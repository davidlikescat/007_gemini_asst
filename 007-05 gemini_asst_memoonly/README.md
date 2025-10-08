# 007-05 gemini_asst_memoonly

Discord 메시지를 노션 메모로 옮기면서 Gemini로 정제본을 만들어 함께 저장하는 최소 구성 프로젝트입니다. 007-04 통합 구조에서 Notion 메모 흐름과 Gemini 정제만 남기고 나머지 에이전트는 제거했습니다.

## 주요 특징
- Discord 메시지를 감지하면 Gemini(Google Generative AI)를 통해 원문을 정제
- 노션 페이지에 **원문 + 정제본**을 모두 저장하고 Discord 메시지 링크까지 남김
- 11-success-logic(ID: 1425020218182467665) 등 차단 채널은 자동 무시
- LangGraph 기반의 최소 상태 관리만 유지해 단일 플로우로 동작

## 준비 사항
`.env` 파일을 `langgraph_agents/.env` 위치에 생성하여 아래 변수를 설정하세요.

```env
DISCORD_TOKEN=디스코드_봇_토큰
DISCORD_CHANNEL_ID=대상_채널_ID              # 선택 사항
BLOCKED_CHANNEL_ID=1425020218182467665       # 선택 사항
NOTION_API_KEY=노션_통합_API_키
NOTION_DATABASE_ID=노션_데이터베이스_ID
NOTION_DEFAULT_STATUS=To Do                  # 선택 사항
NOTION_DEFAULT_PRIORITY=Medium               # 선택 사항
GEMINI_API_KEY=구글_Gemini_API_키
GEMINI_LLM_MODEL=gemini-1.5-flash            # 선택 사항
GEMINI_TEMPERATURE=0.4                       # 선택 사항
GEMINI_MAX_TOKENS=1024                       # 선택 사항
```

## 실행
```bash
pip install -r requirements.txt
python improved_discord_bot.py
```

또는 `python start_bot.py` 로 동일하게 실행할 수 있습니다.

## 007-04 대비 변경점
- Gemini 정제 로직을 LangChain 기반으로 새로 구성
- Notion 저장 시 원문/정제본/Discord 링크를 모두 블록으로 생성
- Gmail·Calendar·Reflection 등 복잡한 그래프 노드를 완전히 제거하고 메모 전용 흐름만 유지
