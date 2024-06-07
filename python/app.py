from fastapi import FastAPI, HTTPException, File, UploadFile, Form
from pydantic import BaseModel
from fastapi.responses import JSONResponse
import boto3
from dotenv import load_dotenv
import os
import deepl
import requests
from openai import OpenAI
import pymysql
import json
import logging
from io import BytesIO
import base64
from fastapi.middleware.cors import CORSMiddleware

dotenv_path='../.env'
load_dotenv(dotenv_path)

app = FastAPI()

# CORS 미들웨어 추가
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 모든 출처에서의 요청을 허용합니다. 필요에 따라 출처를 변경할 수 있습니다.
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE"],  # 허용되는 HTTP 메서드 설정
    allow_headers=["*"],  # 모든 헤더를 허용합니다. 필요에 따라 특정 헤더만 허용할 수 있습니다.
)

# MySQL RDS 연결 설정
host = os.getenv('RDS_HOST')
port = int(os.getenv('RDS_PORT'))
user = os.getenv('RDS_USER')
password = os.getenv('RDS_PW')
database = os.getenv('RDS_DB')

# RDS 연결 생성
connection = pymysql.connect(
    host=host,
    port=port,
    user=user,
    password=password,
    database=database
)

# OCR

# AWS Textract 클라이언트 설정
textract_client = boto3.client(
    'textract',
    region_name=os.getenv('AWS_REGION'),
    aws_access_key_id=os.getenv('AWS_ID'),
    aws_secret_access_key=os.getenv('AWS_SECRET')
)

# 이미지 업로드 및 Textract로 텍스트 추출
@app.post("/textExtractor")
async def textExtractor(file: UploadFile = File(...), filename: str = Form(...)):
    try:
        # 파일을 읽고 처리하는 로직 추가
        contents = await file.read()
        print()
        print(filename)

        # Textract를 사용하여 문서에서 텍스트 추출
        response = textract_client.detect_document_text(
            Document={'Bytes': contents}
        )

        # 추출된 텍스트와 위치 정보를 구성
        extracted_data = []
        for item in response['Blocks']:
            if item['BlockType'] == 'LINE':
                text = item['Text']
                geometry = item['Geometry']
                extracted_data.append({
                    "text": text,
                    "geometry": geometry
                })
        
        # 추출된 데이터를 MySQL에 삽입
        try:
            with connection.cursor() as cursor:
                insert_sql = """
                    INSERT INTO ExtractedTexts (menu_id, extracted_text) VALUES (%s,%s)
                """
                extracted_text = json.dumps(extracted_data)
                cursor.execute(insert_sql, (filename, extracted_text))
            connection.commit()
        except Exception as e:
            connection.rollback()
            print(f"Error: {e}")
            raise HTTPException(status_code=500, detail=f"Database insertion error: {str(e)}")

        return {"extracted_data": json.loads(extracted_text)}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# Translation

deepl_api_url = "https://api.deepl.com/v2/translate"
auth_key = os.getenv('DEEPL_API')
translator = deepl.Translator(auth_key)

# DeepL로 텍스트 번역

class FilenameRequest(BaseModel):
    filename: str

@app.post("/textTranslator")
async def text_translator(request: FilenameRequest):
    filename = request.filename
    print(filename)
    try:
        # MySQL에서 번역할 row 가져오기
        with connection.cursor() as cursor:
            select_sql = f"""
                SELECT extracted_text FROM ExtractedTexts WHERE menu_id = '{filename}'
            """
            cursor.execute(select_sql)
            result = cursor.fetchone()
            if result is None:
                raise HTTPException(status_code=404, detail="Menu not found")
            extracted_text = result[0]

            data = json.loads(extracted_text)
            texts = [item["text"] for item in data]
            

        # 번역 요청
        translated_texts = []
        for text in texts:
            translation_result = translator.translate_text(text, target_lang='ko')
            translated_texts.append(translation_result.text)

        # 번역 결과 저장
        with connection.cursor() as cursor:
            for extracted_text, translated_text in zip(texts, translated_texts):
                insert_sql = """
                    INSERT INTO TranslatedTexts (menu_id, extracted_text, translated_text) VALUES (%s, %s, %s)
                """
                cursor.execute(insert_sql, (filename,extracted_text, translated_text))
        connection.commit()

        return {"translated_texts": translated_texts}

    except Exception as e:
        logging.error(str(e))
        raise HTTPException(status_code=500, detail="Translation failed")


# Image Generation

# OpenAI API 키 설정
OpenAI.api_key = os.getenv("OPENAI_API_KEY")

# S3 키 설정
s3_client = boto3.client(
    's3',
    aws_access_key_id=os.getenv('S3_ID'),
    aws_secret_access_key=os.getenv('S3_SECRET'),
    region_name=os.getenv('S3_REGION')
)
bucket_name = os.getenv('S3_BUCKET')

client = OpenAI()

@app.post("/generateFoodImage")
async def generateFoodImage(extracted_text: str):
    try:
        response = client.images.generate(
            model="dall-e-3",
            prompt=extracted_text,
            size="1024x1024",
            quality="standard",
            n=1,
            )
        image_url = response.data[0].url

        # 이미지 다운로드
        image_response = requests.get(image_url)
        if image_response.status_code != 200:
            raise HTTPException(status_code=500, detail="Failed to download image")

        # 이미지 데이터를 Blob으로 변환
        image_data = image_response.content

        # 이미지 데이터를 base64로 인코딩
        image_data_base64 = base64.b64encode(image_data)

        # 이미지를 MySQL RDS에 저장
        with connection.cursor() as cursor:
            insert_sql = """
                INSERT INTO GeneratedImages (extracted_text, image_data) VALUES (%s, %s)
            """
            cursor.execute(insert_sql, (extracted_text, image_data_base64))
        connection.commit()

        return {
            "extracted_text": extracted_text,
            "image_data_base64": image_data_base64.decode('utf-8')  # base64 데이터를 문자열로 변환
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# Details Generation

@app.post("/getDetails")
async def getDetails(food: str):
    try:
        # 메뉴 설명 생성
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "user", "content": f"{food}가 뭐야?"},
                {"role": "assistant", "content": "짧게 설명해 줘."},
            ]
        )
        description = response.choices[0].message.content

        # 메뉴 재료 생성
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "user", "content": f"{food}의 주재료는 뭐야?"},
                {"role": "assistant", "content": "재료를 python list 형식으로 나열해줘."},
            ]
        )
        ingredients = response.choices[0].message.content

        with connection.cursor() as cursor:
            # 생성된 데이터를 데이터베이스에 삽입
            insert_sql = """
                INSERT INTO FoodDetails (food, description, ingredients) VALUES (%s, %s, %s)
            """
            cursor.execute(insert_sql, (food, description, ingredients))
        
        connection.commit()
        

        return {"description": description, "ingredients": ingredients}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# 번역 데이터 조회
@app.get("/getTranslatedData")
async def getTranslatedData(menu_id: str):
    try:
        with connection.cursor() as cursor:
            select_sql = f"""
                SELECT extracted_text, translated_text FROM TranslatedTexts WHERE menu_id = '{menu_id}'
            """
            cursor.execute(select_sql)
            rows = cursor.fetchall()

            # 'extracted_text'와 'translated_text' 컬럼만 추출하여 새로운 리스트 생성
            translated_texts = []
            for row in rows:
                translated_texts.append({
                    "extracted_text": row[0],
                    "translated_text": row[1]
                })

            return {"translated_texts": translated_texts}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# 생성 데이터 조회
@app.get("/getGenelatedData")
async def getGenelatedData(food: str):
    try:
        with connection.cursor() as cursor:
            select_sql = f"""
                SELECT image_url FROM FoodImages WHERE extracted_text = '{food}'
            """
            cursor.execute(select_sql)
            result = cursor.fetchone()
            image_id = result[0].split('/')[-1]
            print(image_id)
            s3_key = "generatedImages/" + image_id
            print(s3_key)

            # 로컬에 이미지 저장
            local_file = '/project2/python/temp/'+image_id
            print(local_file)
            s3_client.download_file(bucket_name, s3_key, local_file)
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))