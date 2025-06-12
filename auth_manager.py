# auth_manager.py
import os
import pickle
import logging
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

logger = logging.getLogger(__name__)

class GoogleAuthManager:
    """Google OAuth Device Flow 인증 관리자"""
    
    def __init__(self):
        self.token_file = 'google_token.pickle'
        self.credentials_file = os.getenv('GOOGLE_CREDENTIALS_FILE', 'credentials.json')
        self.scopes = [
            'https://www.googleapis.com/auth/calendar.events',
            'https://www.googleapis.com/auth/calendar'
        ]
        
    def get_credentials(self):
        """저장된 토큰을 로드하거나 새로 인증"""
        creds = None
        
        # 기존 토큰 파일 확인
        if os.path.exists(self.token_file):
            logger.info("기존 토큰 파일을 로드합니다...")
            with open(self.token_file, 'rb') as token:
                creds = pickle.load(token)
        
        # 토큰이 없거나 유효하지 않은 경우
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                logger.info("토큰을 갱신합니다...")
                try:
                    creds.refresh(Request())
                    logger.info("토큰 갱신 성공!")
                except Exception as e:
                    logger.warning(f"토큰 갱신 실패: {e}. 재인증을 진행합니다.")
                    creds = self._device_flow_auth()
            else:
                logger.info("새로운 인증을 진행합니다...")
                creds = self._device_flow_auth()
            
            # 토큰 저장
            with open(self.token_file, 'wb') as token:
                pickle.dump(creds, token)
                logger.info("토큰이 저장되었습니다.")
        
        return creds
    
    def _device_flow_auth(self):
        """Device Flow를 사용한 OAuth 인증"""
        if not os.path.exists(self.credentials_file):
            raise FileNotFoundError(
                f"OAuth 클라이언트 파일을 찾을 수 없습니다: {self.credentials_file}\n"
                "Google Cloud Console에서 OAuth 2.0 클라이언트 ID를 생성하고 "
                "JSON 파일을 다운로드하여 프로젝트 디렉토리에 저장하세요."
            )
        
        # Device Flow 설정
        flow = InstalledAppFlow.from_client_secrets_file(
            self.credentials_file, 
            self.scopes
        )
        
        # 콘솔 기반 인증 (브라우저 자동 실행 안함)
        print("\n" + "="*60)
        print("🔐 Google OAuth 인증이 필요합니다!")
        print("="*60)
        print("VM에서는 브라우저가 없으므로 Device Flow를 사용합니다.")
        print("다음 단계를 따라주세요:\n")
        
        # 최신 버전 호환을 위한 인증 방법
        try:
            # 최신 버전에서는 run_local_server()를 사용하되 포트 0으로 설정
            creds = flow.run_local_server(port=0, open_browser=False)
        except Exception as e:
            logger.warning(f"로컬 서버 방식 실패: {e}")
            # 대안: 수동 인증 코드 입력 방식
            try:
                # 인증 URL 생성
                auth_url, _ = flow.authorization_url(prompt='consent')
                print(f"다음 URL을 브라우저에서 열어주세요:")
                print(f"{auth_url}")
                print("\n인증 완료 후 리디렉션 URL에서 'code=' 다음의 코드를 복사하세요.")
                code = input("인증 코드를 입력하세요: ").strip()
                
                # 코드를 사용해서 토큰 요청
                flow.fetch_token(code=code)
                creds = flow.credentials
            except Exception as manual_error:
                logger.error(f"수동 인증도 실패: {manual_error}")
                raise manual_error
        
        print("\n✅ 인증이 완료되었습니다!")
        print("이제 Google Calendar API를 사용할 수 있습니다.")
        print("="*60)
        
        return creds
    
    def build_calendar_service(self):
        """인증된 Google Calendar 서비스 생성"""
        creds = self.get_credentials()
        return build('calendar', 'v3', credentials=creds)
    
    def test_connection(self):
        """연결 테스트"""
        try:
            service = self.build_calendar_service()
            
            # 캘린더 목록 조회로 테스트
            calendars = service.calendarList().list().execute()
            calendar_count = len(calendars.get('items', []))
            
            logger.info(f"✅ Google Calendar 연결 성공! ({calendar_count}개 캘린더 접근 가능)")
            return True, f"{calendar_count}개 캘린더 접근 가능"
            
        except Exception as e:
            logger.error(f"❌ Google Calendar 연결 실패: {e}")
            return False, str(e)