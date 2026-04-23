import os
import streamlit as st
from dotenv import load_dotenv

if os.path.exists(".env"):
    load_dotenv()

def get_secret(key: str):
    value = os.getenv(key) or st.secrets.get(key)
    if value is None:
        raise ValueError(f"Missing config: {key}")
    return value

APIS_DATA_KEY = get_secret("APIS_DATA_KEY")
NAVER_CLIENT_ID = get_secret("NAVER_CLIENT_ID")
NAVER_CLIENT_SECRET = get_secret("NAVER_CLIENT_SECRET")