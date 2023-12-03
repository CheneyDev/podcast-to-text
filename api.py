import os
from fastapi import FastAPI, HTTPException
import transcription
from dotenv import load_dotenv

app = FastAPI()

load_dotenv()  # 加载.env文件中的环境变量


@app.post("/transcribe/")
async def transcribe(url: str):
    try:
        api_key = os.getenv("OPENAI_API_KEY")
        api_server = os.getenv("API_SERVER")
        resend_api_key = os.getenv("RESEND_API_KEY")
        email_sender = os.getenv("SENDER_EMAIL")
        email_receiver = os.getenv("RECEIVER_EMAIL")
        print(api_server)
        result = transcription.process_audio_and_send_email(
            url, api_key, api_server, resend_api_key, email_sender, email_receiver
        )
        return {"transcription": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
