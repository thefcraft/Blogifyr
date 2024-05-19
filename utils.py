from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.backends import default_backend
from werkzeug.utils import secure_filename
import hashlib
import os
import re
import uuid
import shortuuid
import markdown2
from bs4 import BeautifulSoup

class IndexCipher:
    def __init__(self, key:str):
        # Apply SHA-256 hash function to the key
        self.hashed_key = hashlib.sha256(key.encode()).digest()
        
    def encode(self, idx:int, key=None)->str:
        return shortuuid.encode(self.encrypt_index(idx=idx, uudi_formated=True, key=key))    
    def decode(self, s:str, key=None)->int:
        return self.decrypt_index(shortuuid.decode(s), key=key)
    
    def encrypt_index(self, idx:int, uudi_formated=True, key=None)->str:
        hashed_key = hashlib.sha256(key.encode()).digest() if key else self.hashed_key
        # Convert the index to bytes
        idx_bytes = str(idx).encode('utf-8')

        # Pad the plaintext to match the block size
        padder = padding.PKCS7(algorithms.AES.block_size).padder()
        padded_data = padder.update(idx_bytes) + padder.finalize()

        # Encrypt the padded plaintext
        cipher = Cipher(algorithms.AES(hashed_key), modes.ECB(), backend=default_backend())
        encryptor = cipher.encryptor()
        encrypted_idx = encryptor.update(padded_data) + encryptor.finalize()
        assert len(encrypted_idx) == 16
        # Convert the encrypted bytes to a UUID-like string
        hex_string = ''.join(['{:02x}'.format(byte) for byte in encrypted_idx])
        if uudi_formated:
            return uuid.UUID(f"{hex_string[:8]}-{hex_string[8:12]}-{hex_string[12:16]}-{hex_string[16:20]}-{hex_string[20:]}")
        else:
            return ''.join([hex_string[i:i+8] for i in range(0, len(hex_string), 8)])

    def decrypt_index(self, encrypted_id:str, key=None)->int:
        hashed_key = hashlib.sha256(key.encode()).digest() if key else self.hashed_key
        # Split the UUID-like string and convert to bytes
        encrypted_bytes = bytes.fromhex(str(encrypted_id).replace('-', ''))

        # Decrypt the encrypted bytes
        cipher = Cipher(algorithms.AES(hashed_key), modes.ECB(), backend=default_backend())
        decryptor = cipher.decryptor()
        decrypted_data = decryptor.update(encrypted_bytes) + decryptor.finalize()

        # Unpad the decrypted data
        unpadder = padding.PKCS7(algorithms.AES.block_size).unpadder()
        unpadded_data = unpadder.update(decrypted_data) + unpadder.finalize()

        # Convert bytes back to the original index
        original_idx = int(unpadded_data.decode('utf-8'))
        return original_idx

def readingTime(markdown_text: str, words_per_minute: int = 200):
    # Remove Markdown-style links and images from the text
    text = re.sub(r'!\[.*?\]\(.*?\)', '', markdown_text)  # Remove images
    text = re.sub(r'\[.*?\]\(.*?\)', '', text)   # Remove links
    
    # Count the number of words in the text
    word_count = len(text.split())

    # Calculate reading time in minutes
    reading_time = word_count // words_per_minute
    return max(reading_time, 1)

def get_url_by_name(name:str):
    return secure_filename(name)

def get_img(markdown_text):
    pattern = r"!\[.*?\][ ]*\((.*?)\)"
    match = re.search(pattern, markdown_text)
    return match.group(1) if match else None

def add_ellipsis(text_content, max_len=100):
    if isinstance(text_content, str):
        return text_content[:max_len-1]+'...' if len(text_content)>=max_len else text_content
    else: 
        return text_content

def get_sub_title(markdown_text):
    html_content = markdown2.markdown(markdown_text)
    soup = BeautifulSoup(html_content, 'html.parser')
    text_content = soup.get_text()
    return add_ellipsis(text_content, 100)

def get_url(title:str, blog_id, key)->str:
    url = title.lower()
    # Replace spaces with dashes
    url = url.replace(' ', '-')
    # Remove special characters
    url = re.sub(r'[^a-zA-Z0-9-]', '', url)
    return f'{url}-{IndexCipher(str(key)).encode(blog_id)}'
def get_id(url:str, key)->int:
    return IndexCipher(str(key)).decode(url.split('-')[-1])
def check_url(url, blog, key:str)->bool:
    if not blog: return False
    return get_url(blog.title, blog_id=blog.id, key=key) == url

if __name__ == '__main__':
    blog_text = """
    # Example Blog Post

    This is a sample blog post content. It may contain multiple paragraphs and various formatting elements such as **bold** or *italic* text.

    ![Example Image](https://example.com/image.png)

    Read more about this topic [here](https://example.com/blog).
    """

    time_in_minutes = readingTime(blog_text)
    print(f"Reading time: {time_in_minutes} minutes")
    import random
    print(get_url("Want to Stand Out in Data Science? Don’t Make These Portfolio Mistakes!", 62, 'abc'))
    print(get_id(get_url("Want to Stand Out in Data Science? Don’t Make These Portfolio Mistakes!", 12, 1), 1))