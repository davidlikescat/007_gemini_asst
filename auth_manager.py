# auth_manager.py - 하이브리드 방식으로 개선

import os
import json
import logging
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

logger = logging.getLogger(__name__)

class GoogleAuthManager:
    def __init__(self):
        """Google 인증 관리자 초기화"""
        self.scopes = [
            'https://www.googleapis.com/auth/calendar',  # 전체 캘린더 권한
            'https://www.googleapis.com/auth/calendar.events',  # 이벤트 권한
            'https://www.googleapis.com/auth/calendar.readonly'  # 읽기 권한
        ]
        self.token_file = 'token.json'
        self.credentials_file = 'credentials.json'
        self.credentials = None
        
    def get_credentials(self):
        """인증 정보 획득 - 하이브리드 방식"""
        creds = None
        
        # 1단계: 기존 토큰 파일 확인
        if os.path.exists(self.token_file):
            logger.info("✅ 기존 토큰 파일을 발견했습니다!")
            try:
                creds = Credentials.from_authorized_user_file(self.token_file, self.scopes)
                logger.info("📁 토큰 파일 로드 성공")
            except Exception as e:
                logger.warning(f"⚠️ 토큰 파일 로드 실패: {e}")
                creds = None
        
        # 2단계: 토큰 갱신 시도
        if creds and creds.expired and creds.refresh_token:
            logger.info("🔄 토큰 갱신을 시도합니다...")
            try:
                creds.refresh(Request())
                logger.info("✅ 토큰 갱신 성공!")
                
                # 갱신된 토큰 저장
                with open(self.token_file, 'w') as token:
                    token.write(creds.to_json())
                logger.info("💾 갱신된 토큰 저장 완료")
                
            except Exception as e:
                logger.error(f"❌ 토큰 갱신 실패: {e}")
                creds = None
        
        # 3단계: 새로운 인증 필요 (로컬에서만)
        if not creds or not creds.valid:
            if os.path.exists(self.credentials_file):
                logger.info("🔐 새로운 인증이 필요합니다...")
                
                # VM 환경 감지
                if self.is_vm_environment():
                    logger.error("🚨 VM 환경에서는 브라우저 인증이 불가능합니다!")
                    logger.error("📋 해결 방법:")
                    logger.error("   1. 로컬 PC에서 봇을 실행하여 token.json 생성")
                    logger.error("   2. token.json 파일을 VM으로 복사")
                    logger.error("   3. VM에서 봇 재실행")
                    raise Exception("VM 환경에서 브라우저 인증 불가. 로컬에서 token.json을 생성하세요.")
                
                # 수동 브라우저 인증 실행
                logger.info("🌐 브라우저 인증을 시작합니다...")
                logger.info("📋 수동으로 인증 코드를 입력하는 방식입니다.")
                
                flow = InstalledAppFlow.from_client_secrets_file(
                    self.credentials_file, self.scopes)
                
                # 인증 URL 생성
                flow.redirect_uri = 'urn:ietf:wg:oauth:2.0:oob'
                auth_url, _ = flow.authorization_url(prompt='consent')
                
                print("\n" + "="*60)
                print("🔐 Google 계정 인증이 필요합니다!")
                print("="*60)
                print(f"1️⃣ 아래 URL을 브라우저에서 열어주세요:")
                print(f"\n{auth_url}\n")
                print("2️⃣ Google 계정으로 로그인하고 권한을 허용하세요")
                print("3️⃣ 표시되는 인증 코드를 복사하세요")
                print("="*60)
                
                # 사용자로부터 인증 코드 입력 받기
                auth_code = input("📝 인증 코드를 입력하세요: ").strip()
                
                # 토큰 획득
                flow.fetch_token(code=auth_code)
                creds = flow.credentials
                
                # 토큰 저장
                with open(self.token_file, 'w') as token:
                    token.write(creds.to_json())
                logger.info("✅ 새 토큰이 저장되었습니다!")
                
            else:
                raise FileNotFoundError(f"❌ {self.credentials_file} 파일이 없습니다!")
        
        self.credentials = creds
        return creds
    
    def is_vm_environment(self):
        """VM 환경인지 감지 - macOS 친화적 버전"""
        import platform
        
        # macOS는 VM이 아님
        if platform.system() == 'Darwin':
            return False
        
        # Windows도 VM이 아님
        if platform.system() == 'Windows':
            return False
        
        # Linux 계열에서만 VM 감지
        vm_indicators = [
            # SSH 연결 확인 (가장 확실한 지표)
            os.getenv('SSH_CLIENT') is not None,
            os.getenv('SSH_TTY') is not None,
            # 가상화 관련 파일들
            os.path.exists('/proc/vz'),
            os.path.exists('/.dockerenv'),
            # systemd-detect-virt 결과 확인 (Linux)
            self._check_virtualization(),
        ]
        
        # 하나라도 해당되면 VM으로 판단
        return any(vm_indicators)
    
    def _check_virtualization(self):
        """Linux에서 가상화 환경 감지"""
        try:
            import subprocess
            result = subprocess.run(['systemd-detect-virt'], 
                                  capture_output=True, text=True, timeout=5)
            return result.returncode == 0 and result.stdout.strip() != 'none'
        except:
            return False
    
    def build_calendar_service(self):
        """Google Calendar 서비스 생성"""
        try:
            creds = self.get_credentials()
            service = build('calendar', 'v3', credentials=creds)
            logger.info("📅 Google Calendar 서비스 생성 완료")
            return service
        except Exception as e:
            logger.error(f"❌ Calendar 서비스 생성 실패: {e}")
            raise e
    
    def test_connection(self):
        """연결 테스트"""
        try:
            service = self.build_calendar_service()
            calendar_list = service.calendarList().list().execute()
            calendar_count = len(calendar_list.get('items', []))
            
            logger.info(f"✅ Google Calendar 연결 성공!")
            return True, f"{calendar_count}개 캘린더 접근 가능"
            
        except Exception as e:
            logger.error(f"❌ 연결 테스트 실패: {e}")
            return False, str(e)
