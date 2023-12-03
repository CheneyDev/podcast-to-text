import os
from urllib.parse import unquote, urlparse
import requests
from bs4 import BeautifulSoup
from pydub import AudioSegment
from fastapi import FastAPI, BackgroundTasks, HTTPException
from pydantic import BaseModel
from dotenv import load_dotenv
import resend

# 加载 .env 文件中的环境变量
load_dotenv()

# FastAPI 应用
app = FastAPI()


# 请求模型
class TranscriptionRequest(BaseModel):
    url: str


# 环境变量
api_key = os.getenv("OPENAI_API_KEY")
api_server = os.getenv("API_SERVER")
resend.api_key = os.getenv("RESEND_API_KEY")
email_sender = os.getenv("SENDER_EMAIL")
email_receiver = os.getenv("RECEIVER_EMAIL")

# 常量
MAX_FILE_SIZE_MB = 23
BYTES_PER_MB = 1024 * 1024


# 发送音频转录请求的函数
def send_audio_transcription_request(
    file_path, api_key, api_server, model="whisper-1", response_format="json"
):
    url = f"{api_server}/v1/audio/transcriptions"
    headers = {
        "Accept": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    files = {
        "file": (file_path, open(file_path, "rb")),
        "model": (None, model),
        "response_format": (None, response_format),
    }
    response = requests.post(url, headers=headers, files=files)
    print(response.text)
    return response


# 后台处理音频的函数
def process_audio(url: str):
    # 获取网页源代码并解析
    response = requests.get(url)
    soup = BeautifulSoup(response.content, "html.parser")

    # 获取音频文件下载地址
    audio_tag = soup.find("meta", {"property": "og:audio"})
    if not audio_tag or "content" not in audio_tag:
        raise ValueError("Audio URL not found in the page")

    title = "podcast_audio"
    audio_url = audio_tag["content"]

    parsed_url = urlparse(unquote(audio_url))
    extension = os.path.splitext(parsed_url.path)[1]

    file_name = f"{title}{extension}"

    # 下载音频文件
    response = requests.get(audio_url)
    audio_data = response.content

    # 保存音频文件到临时文件
    temp_file_path = "temp_" + file_name
    with open(temp_file_path, "wb") as f:
        f.write(audio_data)

    # 加载音频文件
    audio = AudioSegment.from_file(temp_file_path)

    # 存储所有分片的文本
    all_transcriptions = []

    # 检查文件大小并分割文件（如果需要）
    file_size = os.path.getsize(temp_file_path)
    if file_size > MAX_FILE_SIZE_MB * BYTES_PER_MB:
        # 计算每个片段的持续时间（以毫秒为单位）
        duration_per_segment_ms = len(audio) / (
            file_size / (MAX_FILE_SIZE_MB * BYTES_PER_MB)
        )

        # 分割并保存音频片段
        start_ms = 0
        part_num = 0
        while start_ms < len(audio):
            end_ms = min(start_ms + duration_per_segment_ms, len(audio))
            segment = audio[start_ms:end_ms]
            segment_file_path = (
                f"{os.path.splitext(temp_file_path)[0]}_part{part_num}.mp3"
            )
            segment.export(segment_file_path, format="mp3")
            start_ms = end_ms
            part_num += 1
            # 发送到API
            api_response = send_audio_transcription_request(
                segment_file_path, api_key, api_server
            )
            # 提取文本并添加到列表中
            transcription_json = api_response.json()
            if "text" in transcription_json:
                all_transcriptions.append(transcription_json["text"])
            # 删除临时文件
            os.remove(segment_file_path)
    else:
        # 如果文件大小未超过限制，发送到API
        api_response = send_audio_transcription_request(
            temp_file_path, api_key, api_server
        )
        # 提取文本并添加到列表中
        transcription_json = api_response.json()
        if "text" in transcription_json:
            all_transcriptions.append(transcription_json["text"])

    # 删除临时音频文件
    os.remove(temp_file_path)

    # 将所有文本合并为一个字符串，每个分片之间用换行符分隔
    merged_transcription = "\n".join(all_transcriptions)

    # 发送邮件
    send_email(
        email_sender, email_receiver, "Transcription Results", merged_transcription
    )


def send_email(sender, recipient, subject, html_content):
    params = {
        "from": f"{sender} <{sender}>",
        "to": [recipient],
        "subject": subject,
        "html": html_content,
    }
    email = resend.Emails.send(params)


@app.post("/transcribe")
async def transcribe(request: TranscriptionRequest, background_tasks: BackgroundTasks):
    # 检查 URL 是否提供
    if not request.url:
        raise HTTPException(status_code=400, detail="No URL provided")

    # 将 process_audio 函数作为后台任务添加
    background_tasks.add_task(process_audio, request.url)

    return {"message": "Transcription started"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
