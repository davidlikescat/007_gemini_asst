import google.generativeai as genai
import json
import os
import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, Any
import re
from notion_client import Client
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# 새로 추가한 인증 관리자 import
from auth_manager import GoogleAuthManager

logger = logging.getLogger(__name__)

class ActionProcessor:
    def __init__(self):
        """액션 처리기 초기화"""
        self.setup_gemini()
        self.setup_google_services()
        self.setup_notion()
        
        # 팀원 이메일 매핑 (기존과 동일)
        self.team_emails = {
            '배홍주': 'hongjubae@lguplus.co.kr',
            '배홍주님': 'hongjubae@lguplus.co.kr',
            '홍주': 'hongjubae@lguplus.co.kr',
            '김준희': 'junecruise2@lguplus.co.kr',
            '김준희님': 'junecruise2@lguplus.co.kr',
            '준희': 'junecruise2@lguplus.co.kr',
            '김은희': 'eun7797@lguplus.co.kr',
            '양준모': 'davidjoonmo@lguplus.co.kr',
            '양준모님': 'davidjoonmo@lguplus.co.kr',
            '최종우': 'ahffk0821@lguplus.co.kr',
            '이종원': 'cruise@lguplus.co.kr',
            '박은경': 'ekgoju@lguplus.co.kr',
            '정지우': 'jiujeong@lguplus.co.kr',
        }
        
        # SMTP 설정 확인
        self.validate_smtp_config()

    def setup_gemini(self):
        """Gemini API 설정 (기존과 동일)"""
        api_key = os.getenv('GEMINI_API_KEY')
        if not api_key:
            raise ValueError("GEMINI_API_KEY가 설정되지 않았습니다!")
        
        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel('models/gemini-1.5-pro')
        logger.info("Gemini API 설정 완료")

    def setup_google_services(self):
        """Google 서비스 설정 - Device Flow 방식"""
        try:
            logger.info("Google 서비스 설정을 시작합니다...")
            
            # Device Flow 인증 관리자 생성
            self.auth_manager = GoogleAuthManager()
            
            # Google Calendar 서비스 생성
            self.calendar_service = self.auth_manager.build_calendar_service()
            
            # 연결 테스트
            success, message = self.auth_manager.test_connection()
            if success:
                logger.info(f"Google Calendar 설정 완료: {message}")
            else:
                logger.error(f"Google Calendar 설정 실패: {message}")
                self.calendar_service = None
                raise Exception(message)
                
        except FileNotFoundError as e:
            logger.error(f"OAuth 클라이언트 파일 오류: {e}")
            self.calendar_service = None
            raise e
        except Exception as e:
            logger.error(f"Google 서비스 설정 실패: {e}")
            self.calendar_service = None
            raise e

    def setup_notion(self):
        """Notion 클라이언트 설정 (기존과 동일)"""
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
            raise e

    def validate_smtp_config(self):
        """SMTP 설정 검증"""
        email_address = os.getenv("EMAIL_ADDRESS")
        email_password = os.getenv("EMAIL_PASSWORD")
        
        if not email_address or not email_password:
            logger.warning("SMTP 설정이 완료되지 않았습니다. 이메일 기능이 제한됩니다.")
        else:
            logger.info("SMTP 설정이 확인되었습니다.")

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
            
            # 이미 처리된 메시지는 건너뛰기
            if hasattr(message, 'processed') and message.processed:
                return {
                    'success': False,
                    'error': '이미 처리된 메시지입니다.'
                }
            
            logger.info(f"메시지 처리 시작: '{content}' by {author}")
            
            analysis = await self.analyze_message_with_gemini(content, author, timestamp)
            
            if not analysis['success']:
                return {
                    'success': False,
                    'error': analysis.get('error', '메시지 분석 실패'),
                    'progress_message': analysis.get('progress_message', '')
                }
            
            action_type = analysis.get('action_type', 'none')
            action_data = analysis['action_data']
            
            logger.info(f"분석 결과: action_type={action_type}")
            
            # 액션별 처리
            if action_type == 'calendar_create':
                result = await self.create_calendar_event(action_data)
            elif action_type == 'calendar_update':
                result = await self.update_calendar_event(action_data)
            elif action_type == 'email':
                result = await self.send_email(action_data, original_content=content)
            elif action_type == 'memo':
                result = await self.save_memo(action_data, content)
            else:
                return {
                    'success': False,
                    'error': f'지원되지 않는 액션: {action_type}'
                }
            
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
        """Gemini를 사용하여 메시지 분석"""
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

다음 중 **가장 적절한 액션 하나만** 선택하고 JSON 형태로 응답해주세요:

1. **calendar_create**: 명확한 일정/미팅/회의/약속 생성 요청
   - 반드시 시간 정보가 포함되어야 함 (날짜 + 시간)
   - 예: "내일 오전 10시 회의", "다음주 금요일 2시 미팅"

2. **calendar_update**: 기존 일정 수정/변경 
   - "수정", "변경", "업데이트" 키워드가 명시적으로 포함된 경우

3. **email**: 명확한 이메일 발송 요청
   - "메일", "이메일", "보내줘", 팀원 이름 언급 시
   - **메일 본문에는 사용자가 요청한 내용(예: 특정 시간/장소 정보, 추가 요청)을 포함해야 합니다.**
   - 예: "홍주님께 메일 보내줘", "김준희에게 이메일"

4. **memo**: 기록/메모가 필요한 모든 내용 (기본값)
   - 아이디어, 생각, 정보, 할 일, 업무 내용
   - 시간 정보가 없는 일반적인 내용
   - 예: "프로젝트 아이디어", "회의록", "업무 정리"

5. **none**: 인사말이나 단순한 대화

**중요한 판단 기준**:
- 시간(날짜+시간)이 명확히 지정된 경우만 calendar_create
- 시간 정보가 없거나 애매한 경우는 memo
- 팀원 이름 + "메일/이메일" 키워드가 있어야만 email
- 의심스러우면 memo를 선택

응답 형식:
{{
    "action_type": "calendar_create|calendar_update|email|memo|none",
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
- "다음달": {(current_time.replace(day=1) + timedelta(days=32)).strftime('%Y-%m-%d')[:-3] + "-01"} (대략적인 다음달 1일)
- "오전 10시": 10:00
- "오후 2시": 14:00

action_data 필드:
- calendar_create: title, description, start_time, end_time, location
- calendar_update: title, description, start_time, end_time, location, update_type
- email: recipient, subject, body
- memo: title, category

JSON 이외의 어떤 텍스트도 포함하지 마세요.
"""

            logger.info("Gemini에 분석 요청 전송")
            response = self.model.generate_content(prompt)
            
            # 응답 로깅 (디버깅용)
            logger.info(f"Gemini 원본 응답: {response.text}")
            
            # 개선된 JSON 추출
            json_match = self.extract_json_from_response(response.text)

            if json_match:
                # 응답 데이터 검증
                action_type = json_match.get('action_type')
                valid_actions = ['calendar_create', 'calendar_update', 'email', 'memo', 'none']
                
                if action_type not in valid_actions:
                    logger.warning(f"Invalid action_type: {action_type}")
                    return {
                        'success': False,
                        'error': f'Invalid action_type: {action_type}'
                    }
                
                # calendar 액션의 필수 필드 검증
                if action_type in ['calendar_create', 'calendar_update']:
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
                logger.error(f"Valid JSON object not found in response: {response.text}")
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

    async def create_calendar_event(self, action_data: Dict[str, Any]) -> Dict[str, Any]:
        """Google Calendar에 일정 추가"""
        try:
            if not self.calendar_service:
                return {'success': False, 'error': 'Google Calendar 서비스가 설정되지 않았습니다.'}
            
            # 필수 필드 유효성 검사
            required_fields = ['title', 'start_time', 'end_time']
            missing_fields = [f for f in required_fields if not action_data.get(f)]
            
            if missing_fields:
                return {
                    'success': False,
                    'error': f'필수 필드가 누락되었습니다: {", ".join(missing_fields)}'
                }
            
            # 시간 형식 검증
            try:
                start_time = datetime.fromisoformat(action_data['start_time'].replace('Z', '+00:00'))
                end_time = datetime.fromisoformat(action_data['end_time'].replace('Z', '+00:00'))
                
                if start_time >= end_time:
                    return {
                        'success': False,
                        'error': '시작 시간이 종료 시간보다 늦을 수 없습니다.'
                    }
            except ValueError as e:
                return {
                    'success': False,
                    'error': f'잘못된 시간 형식: {str(e)}'
                }
            
            # 이벤트 생성
            event = {
                'summary': action_data['title'],
                'description': action_data.get('description', ''),
                'start': {
                    'dateTime': action_data['start_time'],
                    'timeZone': 'Asia/Seoul',
                },
                'end': {
                    'dateTime': action_data['end_time'],
                    'timeZone': 'Asia/Seoul',
                },
            }

            if action_data.get('location'):
                event['location'] = action_data['location']

            logger.info(f"캘린더 이벤트 생성 시도: {event}")
            created_event = self.calendar_service.events().insert(
                calendarId='primary',
                body=event
            ).execute()
            
            logger.info(f"캘린더 이벤트 생성 성공: {created_event['id']}")
            
            # 이벤트 URL 생성 시 @ 문자열 인코딩
            event_id = created_event['id'].replace('@', '%40')
            
            return {
                'success': True,
                'response_message': f"✅ **일정 생성 완료!**\n📅 **제목**: {action_data['title']}\n🕐 **시작**: {action_data['start_time']}\n🕑 **종료**: {action_data['end_time']}\n📍 **장소**: {action_data.get('location', '미지정')}\n🔗 **Google Calendar에서 확인 가능**",
                'event_id': created_event['id'],
                'details': {
                    'title': action_data['title'],
                    'start_time': action_data['start_time'],
                    'end_time': action_data['end_time'],
                    'location': action_data.get('location'),
                    'calendar_url': "https://calendar.google.com/calendar/u/0/r"
                }
            }

        except Exception as e:
            logger.error(f"캘린더 일정 생성 실패: {str(e)}")
            return {
                'success': False,
                'error': f'일정 생성 실패: {str(e)}'
            }

    async def find_recent_event(self, title_keyword: str) -> Dict[str, Any]:
        """최근 생성된 이벤트 찾기"""
        try:
            if not self.calendar_service:
                return {'success': False, 'error': 'Google Calendar 서비스가 설정되지 않았습니다.'}
            
            # 최근 7일간의 이벤트 검색
            now = datetime.now().isoformat() + 'Z'
            week_ago = (datetime.now() - timedelta(days=7)).isoformat() + 'Z'
            
            events_result = self.calendar_service.events().list(
                calendarId='primary',
                timeMin=week_ago,
                timeMax=now,
                maxResults=50,
                singleEvents=True,
                orderBy='updated'
            ).execute()
            
            events = events_result.get('items', [])
            
            # 제목에 키워드가 포함된 가장 최근 이벤트 찾기
            for event in reversed(events):  # 최신순으로 검색
                event_title = event.get('summary', '').lower()
                if title_keyword.lower() in event_title:
                    return {
                        'success': True,
                        'event': event
                    }
            
            return {'success': False, 'error': f'"{title_keyword}" 관련 최근 이벤트를 찾을 수 없습니다.'}
            
        except Exception as e:
            logger.error(f"이벤트 검색 실패: {str(e)}")
            return {'success': False, 'error': f'이벤트 검색 실패: {str(e)}'}

    async def update_calendar_event(self, action_data: Dict[str, Any]) -> Dict[str, Any]:
        """Google Calendar 일정 수정"""
        try:
            if not self.calendar_service:
                return {'success': False, 'error': 'Google Calendar 서비스가 설정되지 않았습니다.'}
            
            # 수정할 이벤트 찾기
            title_keyword = action_data.get('title', '')
            find_result = await self.find_recent_event(title_keyword)
            
            if not find_result['success']:
                return {
                    'success': False,
                    'error': f'수정할 이벤트를 찾을 수 없습니다: {find_result["error"]}',
                    'solution': [
                        '1. 정확한 일정 제목을 포함해서 요청해주세요',
                        '2. 최근 7일 내에 생성된 일정만 수정 가능합니다',
                        '3. 예: "팀회의 시간 변경해줘"'
                    ]
                }
            
            event = find_result['event']
            event_id = event['id']
            
            # 기존 이벤트 정보 유지하면서 필요한 부분만 업데이트
            updated_event = {
                'summary': action_data.get('title', event.get('summary')),
                'description': action_data.get('description', event.get('description', '')),
                'start': {
                    'dateTime': action_data.get('start_time', event['start'].get('dateTime')),
                    'timeZone': 'Asia/Seoul',
                },
                'end': {
                    'dateTime': action_data.get('end_time', event['end'].get('dateTime')),
                    'timeZone': 'Asia/Seoul',
                },
            }

            if action_data.get('location'):
                updated_event['location'] = action_data['location']
            elif event.get('location'):
                updated_event['location'] = event['location']

            # 이벤트 업데이트
            updated = self.calendar_service.events().update(
                calendarId='primary',
                eventId=event_id,
                body=updated_event
            ).execute()
            
            return {
                'success': True,
                'response_message': f"✅ **일정 수정 완료!**\n📅 **제목**: {updated_event.get('summary')}\n🕐 **시작**: {updated_event['start']['dateTime']}\n🕑 **종료**: {updated_event['end']['dateTime']}\n📍 **장소**: {updated_event.get('location', '미지정')}\n🔗 **Google Calendar에서 확인 가능**",
                'event_id': updated['id'],
                'details': {
                    'title': updated_event.get('summary'),
                    'start_time': updated_event['start']['dateTime'],
                    'end_time': updated_event['end']['dateTime'],
                    'location': updated_event.get('location'),
                    'calendar_url': f"https://calendar.google.com/calendar/event?eid={updated['id']}"
                }
            }

        except Exception as e:
            logger.error(f"캘린더 일정 수정 실패: {str(e)}")
            return {
                'success': False,
                'error': f'일정 수정 실패: {str(e)}'
            }

    async def generate_email_subject(self, original_content: str, recipient_name: str) -> str:
        """Gemini를 사용해서 이메일 제목 생성"""
        try:
            prompt = f"""
다음 Discord 메시지를 바탕으로 적절한 이메일 제목을 생성해주세요.

원본 메시지: "{original_content}"
수신자: {recipient_name}

제목 생성 규칙:
1. 20자 이내로 간결하게
2. 업무 메일에 적합한 공식적인 톤
3. 핵심 내용을 명확히 전달
4. 한글로 작성

제목만 출력하세요. 다른 설명은 포함하지 마세요.
"""
            
            response = self.model.generate_content(prompt)
            subject = response.text.strip().strip('"').strip("'")
            
            # 기본값 설정
            if not subject or len(subject) > 50:
                subject = "업무 관련 문의사항"
            
            return subject
            
        except Exception as e:
            logger.error(f"이메일 제목 생성 실패: {str(e)}")
            return "업무 관련 문의사항"

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


{original_request}

감사합니다."""

    async def send_email(self, action_data: Dict[str, Any], original_content: str = "") -> Dict[str, Any]:
        """SMTP를 사용한 이메일 발송"""
        try:
            # 환경변수 확인
            from_address = os.getenv("EMAIL_ADDRESS")
            password = os.getenv("EMAIL_PASSWORD")
            
            if not from_address or not password:
                return {
                    'success': False,
                    'error': 'SMTP 설정이 완료되지 않았습니다.',
                    'error_code': 'SMTP_CONFIG_MISSING'
                }
            
            # 수신자 정보 처리
            recipient_name = action_data.get('recipient', '')
            recipient_email = self.team_emails.get(recipient_name)
            
            if not recipient_email:
                return {
                    'success': False,
                    'error': f'"{recipient_name}"의 이메일 주소를 찾을 수 없습니다.',
                    'available_contacts': list(self.team_emails.keys()),
                    'error_code': 'RECIPIENT_NOT_FOUND'
                }
            
            # 🔥 핵심 수정: 템플릿 강제 적용
            # Gemini가 생성한 내용 무시하고 템플릿 함수 사용
            logger.info("이메일 템플릿 생성 중...")
            
            # 항상 템플릿 함수를 사용하여 제목과 내용 생성
            subject = await self.generate_email_subject(original_content, recipient_name)
            body = await self.generate_professional_email_content(original_content, recipient_name)
            
            logger.info(f"생성된 제목: {subject}")
            logger.info(f"생성된 내용: {body[:100]}...")
            
            # 이메일 메시지 구성
            msg = MIMEMultipart()
            msg['From'] = from_address
            msg['To'] = recipient_email
            msg['Subject'] = subject
            
            msg.attach(MIMEText(body, 'plain', 'utf-8'))
            
            # SMTP 서버 연결 및 발송
            server = smtplib.SMTP('smtp.gmail.com', 587)
            server.starttls()
            server.login(from_address, password)
            
            text = msg.as_string()
            server.sendmail(from_address, recipient_email, text.encode('utf-8'))
            server.quit()
            
            logger.info(f"이메일 발송 성공: {recipient_email}")
            
            return {
                'success': True,
                'response_message': f"✅ **이메일 발송 완료!**\n📧 **수신자**: {recipient_name} ({recipient_email})\n📝 **제목**: {subject}\n✉️ **내용 미리보기**: {body[:100]}...",
                'details': {
                    'recipient': recipient_name,
                    'recipient_email': recipient_email,
                    'subject': subject,
                    'body': body
                }
            }
            
        except Exception as e:
            logger.error(f"이메일 발송 실패: {str(e)}")
            return {
                'success': False,
                'error': f'이메일 발송 실패: {str(e)}',
                'error_code': 'EMAIL_SEND_FAILED'
            }

    async def save_memo(self, action_data: Dict[str, Any], original_content: str) -> Dict[str, Any]:
        """Notion 데이터베이스에 메모 저장"""
        try:
            if not self.notion or not self.notion_database_id:
                return {
                    'success': False,
                    'error': 'Notion 설정이 완료되지 않았습니다.',
                    'error_code': 'NOTION_CONFIG_MISSING'
                }
            
            # 메모 제목과 카테고리 설정
            title = action_data.get('title', original_content[:50] + '...' if len(original_content) > 50 else original_content)
            category = action_data.get('category', '일반')
            
            # 현재 시간 (한국 시간)
            kst = timezone(timedelta(hours=9))
            current_time = datetime.now(kst)
            
            # Notion 페이지 생성
            new_page = {
                "parent": {"database_id": self.notion_database_id},
                "properties": {
                    "Name": {
                        "title": [
                            {
                                "text": {
                                    "content": title
                                }
                            }
                        ]
                    },
                    "카테고리": {
                        "rich_text": [
                            {
                                "text": {
                                    "content": category
                                }
                            }
                        ]
                    },
                    "생성일": {
                        "date": {
                            "start": current_time.isoformat()
                        }
                    }
                }
            }
            
            response = self.notion.pages.create(**new_page)
            page_id = response['id']
            page_url = response['url']
            
            logger.info(f"Notion 메모 저장 성공: {page_id}")
            
            return {
                'success': True,
                'response_message': f"📝 **메모 저장 완료!**\n📋 **제목**: {title}\n🏷️ **카테고리**: {category}\n🔗 **[Notion에서 보기]({page_url})**",
                'details': {
                    'title': title,
                    'category': category,
                    'content': original_content,
                    'notion_page_id': page_id,
                    'notion_url': page_url,
                    'created_at': current_time.isoformat()
                }
            }
            
        except Exception as e:
            logger.error(f"Notion 메모 저장 실패: {str(e)}")
            return {
                'success': False,
                'error': f'메모 저장 실패: {str(e)}',
                'error_code': 'NOTION_SAVE_FAILED'
            }
