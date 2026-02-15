from dotenv import load_dotenv
load_dotenv()
import os
from pinecone import Pinecone
pc_client = Pinecone(api_key=os.getenv('PINECONE_API_KEY'))

index = pc_client.Index(host="langchat-mzyhl93.svc.aped-4627-b74a.pinecone.io")
