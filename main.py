import os
import requests
from bs4 import BeautifulSoup
from pydub import AudioSegment
from dotenv import load_dotenv
import json

# 加载 .env 文件中的环境变量
load_dotenv()

# 从 .env 文件获取环境变量
api_key = os.getenv('OPENAI_API_KEY')
api_server = os.getenv('API_SERVER')

# 定义常量
MAX_FILE_SIZE_MB = 23
BYTES_PER_MB = 1024 * 1024

# 发送音频转录请求的函数
def send_audio_transcription_request(file_path, api_key, api_server, model='whisper-1', response_format='json'):
    url = f'{api_server}/v1/audio/transcriptions'
    headers = {
        'Accept': 'application/json',
        'Authorization': f'Bearer {api_key}',
    }
    files = {
        'file': ('audio.mp3', open(file_path, 'rb')),
        'model': (None, model),
        'response_format': (None, response_format),
    }
    response = requests.post(url, headers=headers, files=files)
    return response

# 存储所有分片的文本
all_transcriptions = []

# 1. 获取用户输入的网址
url = 'https://www.xiaoyuzhoufm.com/episode/653bb7d2040778d37ad048c6'

# 2. 获取网页源代码并解析
response = requests.get(url)
soup = BeautifulSoup(response.content, 'html.parser')

# 3. 获取音频文件下载地址
audio_tag = soup.find('meta', {'property': 'og:audio'})

title = 'podcast_audio'
audio_url = audio_tag['content']

# 4. 下载音频文件
response = requests.get(audio_url)
audio_data = response.content

# 5. 保存音频文件到临时文件
temp_file_path = os.path.join(os.getcwd(), "temp_" + title)
with open(temp_file_path, "wb") as f:
    f.write(audio_data)

# 6. 加载音频文件
audio = AudioSegment.from_file(temp_file_path)

# 7. 检查文件大小并分割文件（如果需要）
file_size = os.path.getsize(temp_file_path)
if file_size > MAX_FILE_SIZE_MB * BYTES_PER_MB:
    # 计算每个片段的持续时间（以毫秒为单位）
    duration_per_segment_ms = len(audio) / (file_size / (MAX_FILE_SIZE_MB * BYTES_PER_MB))

    # 分割并保存音频片段
    start_ms = 0
    part_num = 0
    while start_ms < len(audio):
        end_ms = min(start_ms + duration_per_segment_ms, len(audio))
        segment = audio[start_ms:end_ms]
        segment_file_path = f"{os.path.splitext(temp_file_path)[0]}_part{part_num}.mp3"
        if os.path.exists(segment_file_path):  # 检查文件是否已存在
            os.remove(segment_file_path)  # 如果存在，则删除
        segment.export(segment_file_path, format="mp3")
        start_ms = end_ms
        part_num += 1
        # 发送到API
        api_response = send_audio_transcription_request(segment_file_path, api_key, api_server)
        # 提取文本并添加到列表中
        transcription_json = api_response.json()
        if 'text' in transcription_json:
            all_transcriptions.append(transcription_json['text'])
        # 删除临时文件
        os.remove(segment_file_path)

else:
    # 如果文件大小未超过限制，则重命名临时文件
    final_file_path = os.path.join(os.getcwd(), title)
    if os.path.exists(final_file_path):  # 检查文件是否已存在
        os.remove(final_file_path)  # 如果存在，则删除
    os.rename(temp_file_path, final_file_path)
    # 发送到API
    api_response = send_audio_transcription_request(final_file_path, api_key, api_server)
    # 提取文本并添加到列表中
    transcription_json = api_response.json()
    if 'text' in transcription_json:
        all_transcriptions.append(transcription_json['text'])

# 将所有文本合并为一个字符串，每个分片之间用换行符分隔
merged_transcription = '\n'.join(all_transcriptions)

# 保存合并后的文本为TXT文件
output_file_path = os.path.join(os.getcwd(), "transcription.txt")
with open(output_file_path, "w", encoding="utf-8") as txt_file:
    txt_file.write(merged_transcription)

print(f"音频文件处理并文本合并完成，已保存到 {output_file_path}！")
