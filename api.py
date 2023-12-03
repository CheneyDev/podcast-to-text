import os
from fastapi import FastAPI, HTTPException
import transcription

app = FastAPI()

@app.post("/transcribe/")
async def transcribe(url: str):
    try:
        api_key = os.getenv('OPENAI_API_KEY')
        api_server = os.getenv('API_SERVER')
        email_sender = os.getenv('SENDER_EMAIL')
        email_receiver = os.getenv('RECEIVER_EMAIL')
        result = transcription.process_audio_and_send_email(url, api_key, api_server, email_sender, email_receiver)
        return {"transcription": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
