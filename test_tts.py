# test_tts.py
import asyncio
import edge_tts

async def main():
    print("1. TTS 시작...")
    try:
        # 가장 기본 목소리로 테스트
        communicate = edge_tts.Communicate("들리나요? 이건 테스트입니다.", "ko-KR-SunHiNeural")
        
        print("2. 서버 요청 중...")
        await communicate.save("check_mic.mp3")
        
        print("3. 성공! 'check_mic.mp3' 파일이 생성되었습니다.")
    except Exception as e:
        print(f"❌ 실패! 에러 내용: {e}")

if __name__ == "__main__":
    asyncio.run(main())