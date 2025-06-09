import google.generativeai as genai
import json
import os
import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, Any
import re
from notion_client import Client

from google.oauth2 import service_account
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
import pickle
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import base64

logger = logging.getLogger(__name__)

class ActionProcessor:
    def __init__(self):
        """ActionProcessor 초기화"""
        self.setup_gemini()
        self.setup_google_services()
        self.setup_notion()
        
        # 팀원 이메일 매핑 (다양한 호칭 포함)
        self.team_emails = {
            '배홍주': 'hongjubae@lguplus.co.kr',
            '배홍주님': 'hongjubae@lguplus.co.kr',
            '홍주': 'hongjubae@lguplus.co.kr',
            '김준희': 'junecruise2@lguplus.co.kr',
            '김준희님': 'junecruise2@lguplus.co.kr',
            '준희': 'junecruise2@lguplus.co.kr',
            '김은희': 'eun7797@lguplus.co.kr',
            '양준모': 'yangjunmo@lguplus.co.kr',
            '양준모님': 'yangjunmo@lguplus.co.kr',
            '최종우': 'ahffk0821@lguplus.co.kr',
            '이종원': 'cruise@lguplus.co.kr',
            '박은경': 'ekgoju@lguplus.co.kr',
            '정지우': 'jiujeong@lguplus.co.kr',
        }
        
    def setup_gemini(self):
        """Gemini API 설정"""
        api_key = os.getenv('GEMINI_API_KEY')
        if not api_key:
            raise ValueError("GEMINI_API_KEY가 설정되지 않았습니다!")
        
        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel('models/gemini-1.5-pro')
        
    def setup_google_services(self):
        """Google 서비스 설정 (OAuth2 기반)"""
        try:
            creds = None
            # 기존 토큰 파일이 있는지 확인
            if os.path.exists('token.pickle'):
                with open('token.pickle', 'rb') as token:
                    creds = pickle.load(token)
            
            # 유효한 크리덴셜이 없거나 만료된 경우
            if not creds or not creds.valid:
                if creds and creds.expired and creds.refresh_token:
                    creds.refresh(Request())
                else:
                    # OAuth2 플로우 시작
                    creds_file = os.getenv('GOOGLE_CREDENTIALS_FILE', 'credentials_oauth.json')
                    scopes = [
                        'https://www.googleapis.com/auth/calendar',
                        'https://www.googleapis.com/auth/gmail.send'
                    ]
                    
                    flow = InstalledAppFlow.from_client_secrets_file(creds_file, scopes)
                    creds = flow.run_local_server(port=0)
                
                # 다음번을 위해 토큰 저장
                with open('token.pickle', 'wb') as token:
                    pickle.dump(creds, token)
            
            self.credentials = creds
            self.calendar_service = build('calendar', 'v3', credentials=creds)
            logger.info("Google OAuth2 서비스 설정 완료")

        except Exception as e:
            logger.warning(f"Google 서비스 설정 실패: {str(e)}")
            self.calendar_service = None

    def setup_notion(self):
        """Notion 클라이언트 설정"""
        try:
            notion_api_key = os.getenv('NOTION_API_KEY')
            notion_database_id = os.getenv('NOTION_DATABASE_ID')
            
            if not notion_api_key:
                raise ValueError("NOTION_API_KEY가 설정되지 않았습니다.")
            
            if not notion_database_id:
                raise ValueError("NOTION_DATABASE_ID가 설정되지 않았습니다.")
                
            self.notion = Client(auth=notion_api_key)
            self.notion_database_id = notion_database_id
            
            logger.info("Notion 클라이언트 설정 완료")
            
        except Exception as e:
            logger.error(f"Notion 설정 실패: {str(e)}")
            raise e  # 오류를 다시 발생시켜 초기화 실패하도록

    def extract_json_from_response(self, text: str) -> Dict[str, Any]:
        """응답에서 JSON 추출 - 개선된 버전"""
        try:
            # 1. 코드 블록 안의 JSON 찾기 (```json ``` 또는 ``` ```)
            code_block_pattern = r'```(?:json)?\s*(\{.*?\})\s*```'
            matches = re.findall(code_block_pattern, text, re.DOTALL)
            
            for match in matches:
                try:
                    parsed = json.loads(match)
                    if isinstance(parsed, dict) and 'action_type' in parsed:
                        logger.info("코드 블록에서 JSON 추출 성공")
                        return parsed
                except json.JSONDecodeError:
                    continue
            
            # 2. 중괄호로 감싸진 JSON 패턴 찾기 (여러 줄 포함)
            json_pattern = r'\{(?:[^{}]|(?:\{[^{}]*\}))*\}'
            matches = re.findall(json_pattern, text, re.DOTALL)
            
            for match in matches:
                try:
                    parsed = json.loads(match)
                    if isinstance(parsed, dict) and 'action_type' in parsed:
                        logger.info("일반 패턴에서 JSON 추출 성공")
                        return parsed
                except json.JSONDecodeError:
                    continue
            
            return None
            
        except Exception as e:
            logger.error(f"JSON 추출 중 오류: {str(e)}")
            return None

    async def process_message(self, message=None, content: str = None, author: str = None, channel: str = None, timestamp: datetime = None) -> Dict[str, Any]:
        """메시지를 분석하고 적절한 액션을 수행"""
        try:
            # message 객체가 있으면 그것에서 정보 추출
            if message:
                content = content or message.content
                author = author or str(message.author)
                channel = channel or str(message.channel)
                timestamp = timestamp or message.created_at
            
            # 진행 상태 메시지 추가
            progress_msg = {
                'step': 'analyzing',
                'message': '🤖 메시지를 분석하고 있습니다...'
            }
            
            analysis = await self.analyze_message_with_gemini(content, author, timestamp)
            
            if not analysis['success']:
                return {
                    **analysis,
                    'progress_message': '❌ 메시지 분석에 실패했습니다.'
                }
            
            action_type = analysis['action_type']
            action_data = analysis['action_data']
            
            # 액션별 진행 메시지
            if action_type == 'calendar':
                progress_msg = {
                    'step': 'processing',
                    'message': '📅 Google Calendar에 일정을 생성하고 있습니다...'
                }
                result = await self.create_calendar_event(action_data)
            elif action_type == 'email':
                progress_msg = {
                    'step': 'processing', 
                    'message': f'📧 {action_data.get("recipient", "수신자")}님께 이메일을 작성하고 발송하고 있습니다...'
                }
                result = await self.send_email(action_data, original_content=content)
            elif action_type == 'memo':
                progress_msg = {
                    'step': 'processing',
                    'message': '📝 Notion에 메모를 저장하고 있습니다...'
                }
                result = await self.save_memo(action_data, content)
            else:
                return {
                    'success': False,
                    'error': '인식된 액션이 없습니다.',
                    'action_type': 'none',
                    'progress_message': '❓ 처리할 수 있는 액션을 찾지 못했습니다.'
                }
            
            # 결과에 진행 정보와 상세 정보 추가
            result['action_type'] = action_type
            result['analysis_confidence'] = analysis.get('confidence', 0.0)
            result['analysis_reasoning'] = analysis.get('reasoning', '')
            
            return result
            
        except Exception as e:
            logger.error(f"메시지 처리 중 오류: {str(e)}")
            return {
                'success': False,
                'error': str(e),
                'action_type': 'error',
                'progress_message': '💥 처리 중 예상치 못한 오류가 발생했습니다.'
            }

    async def analyze_message_with_gemini(self, content: str, author: str, timestamp: datetime) -> Dict[str, Any]:
        """Gemini를 사용하여 메시지 분석 - 개선된 프롬프트"""
        try:
            # 현재 시간 정보 추가
            kst = timezone(timedelta(hours=9))
            current_time = datetime.now(kst)
            
            prompt = f"""
다음 디스코드 메시지를 분석하여 JSON으로만 응답해주세요. 설명이나 다른 텍스트는 절대 포함하지 마세요.

메시지 내용: "{content}"
작성자: {author}
작성시간: {timestamp.strftime('%Y-%m-%d %H:%M:%S')} (한국시간)
현재시간: {current_time.strftime('%Y-%m-%d %H:%M:%S')} (한국시간)

다음 중 **가장 중요한 액션 하나만** 선택하고 JSON 형태로 응답해주세요:

1. calendar: 일정/미팅/회의/약속 관련 (최우선)
2. email: 이메일 발송이 필요한 내용인 경우  
3. memo: 기록/메모가 필요한 일반적인 내용인 경우
4. none: 특별한 액션이 필요하지 않은 경우

**우선순위**: calendar > email > memo > none

응답 형식:
{{
    "action_type": "calendar|email|memo|none",
    "confidence": 0.95,
    "reasoning": "판단근거",
    "action_data": {{
        "title": "제목",
        "start_time": "YYYY-MM-DD HH:MM",
        "end_time": "YYYY-MM-DD HH:MM"
    }}
}}

시간 변환 규칙:
- "내일": {(current_time + timedelta(days=1)).strftime('%Y-%m-%d')}
- "다음주": {(current_time + timedelta(days=7)).strftime('%Y-%m-%d')}
- "오전 10시": 10:00
- "오후 2시": 14:00

action_data 필드:
- calendar: title, description, start_time, end_time, location
- email: recipient, subject, body
- memo: title, category

JSON 이외의 어떤 텍스트도 포함하지 마세요.
"""

            response = self.model.generate_content(prompt)
            
            # 응답 로깅 (디버깅용)
            logger.info(f"Gemini 원본 응답: {response.text}")
            
            # 개선된 JSON 추출
            json_match = self.extract_json_from_response(response.text)

            if json_match:
                # 응답 데이터 검증
                action_type = json_match.get('action_type')
                if action_type not in ['calendar', 'email', 'memo', 'none']:
                    logger.warning(f"Invalid action_type: {action_type}")
                    return {
                        'success': False,
                        'error': f'Invalid action_type: {action_type}'
                    }
                
                # calendar 액션의 필수 필드 검증
                if action_type == 'calendar':
                    action_data = json_match.get('action_data', {})
                    required_fields = ['title', 'start_time', 'end_time']
                    missing_fields = [f for f in required_fields if not action_data.get(f)]
                    
                    if missing_fields:
                        logger.warning(f"Missing required fields for calendar: {missing_fields}")
                        return {
                            'success': False,
                            'error': f'Missing required fields: {missing_fields}'
                        }
                    
                    # 시간 포맷 검증 및 변환
                    try:
                        start_time = action_data['start_time']
                        end_time = action_data['end_time']
                        
                        # YYYY-MM-DD HH:MM 형태로 변환
                        if len(start_time.split()) == 2:  # 날짜와 시간이 분리되어 있는 경우
                            start_datetime = datetime.strptime(start_time, '%Y-%m-%d %H:%M')
                            end_datetime = datetime.strptime(end_time, '%Y-%m-%d %H:%M')
                            
                            # ISO 형태로 변환 (Google Calendar API 호환)
                            action_data['start_time'] = start_datetime.isoformat()
                            action_data['end_time'] = end_datetime.isoformat()
                        
                    except ValueError as e:
                        logger.warning(f"시간 포맷 오류: {e}")
                        return {
                            'success': False,
                            'error': f'시간 포맷 오류: {e}'
                        }
                
                logger.info(f"분석 성공: {action_type}, 신뢰도: {json_match.get('confidence', 0.0)}")
                
                return {
                    'success': True,
                    'action_type': action_type,
                    'action_data': json_match.get('action_data', {}),
                    'confidence': json_match.get('confidence', 0.0),
                    'reasoning': json_match.get('reasoning', '')
                }
            else:
                logger.error(f"Valid JSON object not found in response")
                return {
                    'success': False,
                    'error': 'Valid JSON object not found in response'
                }

        except Exception as e:
            logger.error(f"Gemini 분석 실패: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }

    async def generate_professional_email_content(self, original_request: str, recipient: str) -> str:
        """Gemini를 사용해서 공식적인 이메일 내용 생성"""
        try:
            prompt = f"""
다음 Discord 메시지를 바탕으로 공식적이고 정중한 업무 메일 내용을 작성해주세요.

원본 요청: "{original_request}"
수신자: {recipient}

다음 템플릿 형식을 따라 작성하세요:

안녕하세요. AICC BPO사업팀 양준모입니다.

[여기에 요청 내용을 정중하고 공식적으로 변환한 내용]

감사합니다.

작성 규칙:
1. 존댓말 사용
2. 업무 메일에 적합한 정중한 톤
3. 구체적이고 명확한 요청 내용
4. 불필요한 설명은 제외하고 핵심만 전달
5. 템플릿 형식을 정확히 따를 것

오직 메일 내용만 출력하세요. 추가 설명이나 따옴표는 넣지 마세요.
"""
            
            response = self.model.generate_content(prompt)
            return response.text.strip()
            
        except Exception as e:
            logger.error(f"이메일 내용 생성 실패: {str(e)}")
            # 기본 템플릿 사용
            return f"""안녕하세요. AICC BPO사업팀 양준모입니다.

요청하신 사항에 대해 안내드립니다.

감사합니다."""

    async def create_calendar_event(self, action_data: Dict[str, Any]) -> Dict[str, Any]:
        """Google Calendar에 일정 추가"""
        try:
            if not self.calendar_service:
                return {'success': False, 'error': 'Google Calendar 서비스가 설정되지 않았습니다.'}
            
            event = {
                'summary': action_data.get('title', '디스코드에서 생성된 일정'),
                'description': action_data.get('description', ''),
                'start': {
                    'dateTime': action_data.get('start_time'),
                    'timeZone': 'Asia/Seoul',
                },
                'end': {
                    'dateTime': action_data.get('end_time'),
                    'timeZone': 'Asia/Seoul',
                },
            }

            if action_data.get('location'):
                event['location'] = action_data['location']

            created_event = self.calendar_service.events().insert(
                calendarId='primary',
                body=event
            ).execute()
            
            return {
                'success': True,
                'response_message': f"✅ **일정 생성 완료!**\n📅 **제목**: {action_data.get('title')}\n⏰ **시간**: {action_data.get('start_time')} - {action_data.get('end_time')}\n📍 **장소**: {action_data.get('location', '미지정')}\n🔗 [Google Calendar에서 확인](https://calendar.google.com/calendar/event?eid={created_event['id']})",
                'event_id': created_event['id'],
                'details': {
                    'title': action_data.get('title'),
                    'start_time': action_data.get('start_time'),
                    'end_time': action_data.get('end_time'),
                    'location': action_data.get('location'),
                    'calendar_url': f"https://calendar.google.com/calendar/event?eid={created_event['id']}"
                },
                'progress_message': f"📅 {action_data.get('title')} 일정을 생성하고 있습니다..."
            }

        except Exception as e:
            logger.error(f"캘린더 일정 생성 실패: {str(e)}")
            return {
                'success': False,
                'error': f'일정 생성 실패: {str(e)}'
            }

    async def send_email(self, action_data: Dict[str, Any], original_content: str = "") -> Dict[str, Any]:
        """Gmail API를 통해 실제 이메일 발송"""
        try:
            if not self.calendar_service:  # Gmail 서비스도 같은 credentials 사용
                return {'success': False, 'error': 'Gmail 서비스가 설정되지 않았습니다.'}
            
            # Gmail 서비스 생성 (기존 credentials 재사용)
            gmail_service = build('gmail', 'v1', credentials=self.credentials)
            
            # 수신자 처리 (이름을 이메일로 변환)
            recipient_name = action_data.get('recipient', '')
            logger.info(f"추출된 수신자 이름: '{recipient_name}'")
            logger.info(f"사용 가능한 팀원: {list(self.team_emails.keys())}")
            
            recipient = self.team_emails.get(recipient_name, recipient_name)
            
            # 이메일 형식 검증
            if '@' not in recipient:
                logger.warning(f"유효하지 않은 이메일 주소: {recipient}")
                return {
                    'success': False,
                    'error': f'유효하지 않은 수신자: {recipient_name}. 사용 가능한 팀원: {", ".join(self.team_emails.keys())}'
                }

            # 이메일 구성
            subject = action_data.get('subject', '업무 요청 사항')
            
            # Gemini를 통해 공식적인 이메일 내용 생성
            body = await self.generate_professional_email_content(
                original_request=original_content,  # 원본 Discord 메시지
                recipient=recipient_name
            )
            
            logger.info(f"생성된 이메일 내용: {body[:100]}...")
            
            # 이메일 메시지 작성
            message = MIMEMultipart()
            message['to'] = recipient
            message['subject'] = subject
            
            # 본문 추가
            message.attach(MIMEText(body, 'plain', 'utf-8'))
            
            # base64로 인코딩
            raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode()
            
            # Gmail API로 전송
            sent_message = gmail_service.users().messages().send(
                userId='me',
                body={'raw': raw_message}
            ).execute()
            
            logger.info(f"이메일 발송 성공: {sent_message['id']}")
            
            return {
                'success': True,
                'response_message': f"✅ **이메일 발송 완료!**\n📧 **수신자**: {recipient_name} ({recipient})\n📋 **제목**: {subject}\n📝 **내용**: {body[:100]}...\n⏰ **발송 시간**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n🔗 [Gmail에서 확인](https://mail.google.com/mail/u/0/#sent/{sent_message['id']})",
                'message_id': sent_message['id'],
                'details': {
                    'recipient': recipient,
                    'recipient_name': recipient_name,
                    'subject': subject,
                    'body_preview': body[:100] + "..." if len(body) > 100 else body,
                    'sent_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    'gmail_url': f"https://mail.google.com/mail/u/0/#sent/{sent_message['id']}"
                },
                'progress_message': f"📧 {recipient_name}님께 이메일을 작성하고 발송하고 있습니다..."
            }
            
        except Exception as e:
            logger.error(f"이메일 발송 실패: {str(e)}")
            return {
                'success': False,
                'error': f'이메일 발송 실패: {str(e)}'
            }

    async def save_memo(self, action_data: Dict[str, Any], original_content: str) -> Dict[str, Any]:
        """Notion에 메모 저장"""
        try:
            if not hasattr(self, 'notion') or not self.notion:
                return {
                    'success': False,
                    'error': 'NOTION_SETUP_ERROR: Notion이 설정되지 않았습니다.',
                    'error_code': 'NOTION_NOT_CONFIGURED',
                    'solution': [
                        '1. .env 파일에 NOTION_API_KEY 추가',
                        '2. .env 파일에 NOTION_DATABASE_ID 추가', 
                        '3. Notion Integration 생성 및 데이터베이스 연결',
                        '설정 가이드: https://developers.notion.com/docs/create-a-notion-integration'
                    ]
                }
            
            # 데이터베이스 스키마 확인 (디버깅용)
            try:
                database = self.notion.databases.retrieve(database_id=self.notion_database_id)
                properties = database.get('properties', {})
                logger.info(f"데이터베이스 속성들: {list(properties.keys())}")
                for prop_name, prop_data in properties.items():
                    logger.info(f"속성 '{prop_name}': 타입 = {prop_data.get('type')}")
            except Exception as debug_e:
                logger.warning(f"데이터베이스 스키마 확인 실패: {debug_e}")
            
            # 현재 시간 (한국 시간)
            kst = timezone(timedelta(hours=9))
            current_time = datetime.now(kst)
            
            # 페이지 생성
            page = self.notion.pages.create(
                parent={"database_id": self.notion_database_id},
                properties={
                    "Name": {  # 제목 -> Name
                        "title": [{
                            "text": {"content": action_data.get('title', '새 메모')}
                        }]
                    },
                    "카테고리": {
                        "rich_text": [{
                            "text": {"content": action_data.get('category', '일반')}
                        }]
                    },
                    "Status": {
                        "status": {  # select -> status
                            "name": "Not started"  # Not Started -> Not started
                        }
                    },
                    "생성일": {
                        "date": {
                            "start": current_time.isoformat()
                        }
                    }
                },
                children=[
                    {
                        "object": "block",
                        "type": "paragraph",
                        "paragraph": {
                            "rich_text": [{
                                "text": {"content": f"원본 내용:\n{original_content}"}
                            }]
                        }
                    }
                ]
            )
            
            return {
                'success': True,
                'response_message': f"✅ **Notion 메모 저장 완료!**\n📝 **제목**: {action_data.get('title')}\n🏷️ **카테고리**: {action_data.get('category', '일반')}\n📊 **상태**: Not started\n📅 **생성일**: {current_time.strftime('%Y-%m-%d %H:%M:%S')}\n🔗 **Notion에서 확인 가능**",
                'page_id': page['id'],
                'details': {
                    'title': action_data.get('title'),
                    'category': action_data.get('category', '일반'),
                    'status': 'Not started',
                    'created_time': current_time.strftime('%Y-%m-%d %H:%M:%S'),
                    'notion_url': f"https://notion.so/{page['id'].replace('-', '')}"
                }
            }
                
        except Exception as e:
            logger.error(f"메모 저장 실패: {str(e)}")
            
            # 구체적인 오류 분석
            error_message = str(e).lower()
            
            if 'unauthorized' in error_message or '401' in error_message:
                return {
                    'success': False,
                    'error': 'NOTION_AUTH_ERROR: Notion 토큰이 유효하지 않습니다.',
                    'error_code': 'INVALID_TOKEN',
                    'solution': [
                        '1. NOTION_API_KEY가 올바른지 확인',
                        '2. Integration이 활성화되어 있는지 확인',
                        '3. 새로운 API 키를 생성해보세요'
                    ]
                }
            elif 'not_found' in error_message or '404' in error_message:
                return {
                    'success': False,
                    'error': 'NOTION_DATABASE_ERROR: 데이터베이스를 찾을 수 없습니다.',
                    'error_code': 'DATABASE_NOT_FOUND',
                    'solution': [
                        '1. NOTION_DATABASE_ID가 올바른지 확인',
                        '2. 데이터베이스에 Integration을 연결했는지 확인',
                        '3. 데이터베이스가 삭제되지 않았는지 확인'
                    ]
                }
            elif 'validation' in error_message:
                return {
                    'success': False,
                    'error': 'NOTION_SCHEMA_ERROR: 데이터베이스 스키마가 올바르지 않습니다.',
                    'error_code': 'INVALID_SCHEMA',
                    'solution': [
                        '1. 데이터베이스에 다음 속성이 있는지 확인:',
                        '   - 제목 (Title)',
                        '   - 카테고리 (Text)',
                        '   - Status (Select)',
                        '   - 생성일 (Date)',
                        '2. 속성 이름이 정확한지 확인'
                    ]
                }
            else:
                return {
                    'success': False,
                    'error': f'NOTION_UNKNOWN_ERROR: {str(e)}',
                    'error_code': 'UNKNOWN_ERROR',
                    'solution': [
                        '1. 네트워크 연결 확인',
                        '2. Notion 서비스 상태 확인',
                        '3. 로그를 확인하여 상세한 오류 내용 파악'
                    ]
                }