import os
from urllib.parse import unquote, urlparse
import requests
from bs4 import BeautifulSoup
from pydub import AudioSegment
from dotenv import load_dotenv
import resend
import json

# 定义常量
MAX_FILE_SIZE_MB = 23
BYTES_PER_MB = 1024 * 1024


def send_audio_transcription_request(
    file_path, api_key, api_server, model="whisper-1", response_format="json"
):
    # 发送音频转录请求的函数
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
    return response.json()


def process_audio_and_send_email(
    url, api_key, api_server, resend_api_key, email_sender, email_receiver
):
    # 1. 获取网页源代码并解析
    response = requests.get(url)
    soup = BeautifulSoup(response.content, "html.parser")

    # 找到包含播客信息的 <script> 标签
    script_tag = soup.find("script", {"name": "schema:podcast-show"})
    # 解析 JSON 数据
    podcast_data = json.loads(script_tag.string)
    # 提取播客系列的信息
    podcast_series = podcast_data.get("partOfSeries", {})
    author_name = podcast_series.get("name")



    # 2. 获取音频文件下载地址
    audio_tag = soup.find("meta", {"property": "og:audio"})
    title_tag = soup.find("meta", {"property": "og:title"})
    cover_tag = soup.find("meta", {"property": "og:image"})

    audio_url = audio_tag["content"]
    audio_title = title_tag["content"]
    sudio_cover = cover_tag["content"]

    print("播客系列名称:", author_name)
    print("音频标题:", audio_title)
    print("音频封面:", sudio_cover)
    print("音频下载地址:", audio_url)
    

    parsed_url = urlparse(unquote(audio_url))

    extension = os.path.splitext(parsed_url.path)[1]
    file_name = f"{title}{extension}"

    # 3. 下载音频文件
    response = requests.get(audio_url)
    audio_data = response.content

    # 4. 保存音频文件到临时文件
    temp_file_path = "temp_" + file_name
    with open(temp_file_path, "wb") as f:
        f.write(audio_data)

    # 5. 加载音频文件
    audio = AudioSegment.from_file(temp_file_path)

    # 6. 检查文件大小并分割文件（如果需要）
    file_size = os.path.getsize(temp_file_path)
    all_transcriptions = []

    if file_size > MAX_FILE_SIZE_MB * BYTES_PER_MB:
        # 计算每个片段的持续时间（以毫秒为单位）
        duration_per_segment_ms = int(len(audio) / (
            file_size / (MAX_FILE_SIZE_MB * BYTES_PER_MB)
        ))

        # 分割并保存音频片段
        start_ms = 0
        part_num = 0
        while start_ms < len(audio):
            end_ms = min(start_ms + duration_per_segment_ms, len(audio))
            segment = audio[start_ms:end_ms]
            segment_file_path = (
                f"{os.path.splitext(temp_file_path)[0]}_part{part_num}.mp3"
            )
            part_num += 1  # 递增part_num，以便每个片段都有不同的文件名
            if os.path.exists(segment_file_path):  # 检查文件是否已存在
                os.remove(segment_file_path)  # 如果存在，则删除
            segment.export(segment_file_path, format="mp3")
            start_ms = end_ms
            # 发送到API
            api_response = send_audio_transcription_request(
                segment_file_path, api_key, api_server
            )
            # 提取文本并添加到列表中
            if "text" in api_response:
                all_transcriptions.append(api_response["text"])
            # 删除临时文件
            os.remove(segment_file_path)
    else:
        # 转录整个音频文件
        response_json = send_audio_transcription_request(
            temp_file_path, api_key, api_server
        )
        if "text" in response_json:
            all_transcriptions.append(response_json["text"])
    
    # 删除临时音频文件
    os.remove(temp_file_path)

    # 7. 将所有文本合并为一个字符串，每个分片之间用换行符分隔
    merged_transcription = "<br>".join(all_transcriptions)
    merged_transcription = merged_transcription.replace(" ", "<br>")

    with open('email_template.html', 'r', encoding='utf-8') as template_file:
        email_html = template_file.read()

    # 替换模板中的占位符
    email_html = email_html.replace('<!--CONTENT_PLACEHOLDER-->', merged_transcription)
    email_html = email_html.replace('<!--TITLE_PLACEHOLDER-->', audio_title)
    email_html = email_html.replace('<!--COVER_PLACEHOLDER-->', audio_cover)
    email_html = email_html.replace('<!--AUTHOR_PLACEHOLDER-->', author_name)


    # 8. 发送邮件
    resend.api_key = resend_api_key
    sender_name = "Podcast to Text"
    params = {
        "from": sender_name + " <" + email_sender + ">",
        "to": [email_receiver],  # 指定收件人的电子邮件地址
        "subject": "Transcription Results",
        "html": email_html,  # 使用合并后的文本作为邮件正文
    }
    resend.Emails.send(params)

if __name__ == "__main__":
    # 加载环境变量
    load_dotenv()

    # 从环境变量中获取所需信息
    api_key = os.getenv("OPENAI_API_KEY")
    api_server = os.getenv("API_SERVER")
    resend_api_key = os.getenv("RESEND_API_KEY")
    email_sender = os.getenv("SENDER_EMAIL")
    email_receiver = os.getenv("RECEIVER_EMAIL")

    # 用于测试的URL
    test_url = "https://www.xiaoyuzhoufm.com/episode/653944eb8f151344dc941a01"

    # 调用函数处理音频并发送邮件
    process_audio_and_send_email(
        test_url, api_key, api_server, resend_api_key, email_sender, email_receiver
    )
