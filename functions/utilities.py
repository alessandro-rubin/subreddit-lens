import pandas as pd
import zstandard as zstd
import io
import json 
import re



def preprocess(text):
    '''Applies basic preprocessing to Reddit comments, removes links, markdown, quotes.'''

    # Remove URLs in square brackets (e.g., [text](link))
    url_pattern = r'\[(.*?)\]\(([^)]+)\)'
    text = re.sub(url_pattern, r'\1', text)

    # Remove quote blocks (e.g., > something \n\n) and preserve line breaks
    quote_pattern = (
        r'(?:(?:^|\s)(\">\s*?(.*?)\s*</>)|(>\s*?(.*?)\s*</>))'
        r'\s*\n(?:\n\s*\n\s*)|(?!\S)'
    )
    text = re.sub(quote_pattern, '', text)

    # Remove line breaks and replace with spaces
    text = re.sub(r'(\n|\t|\\|&amp;)', ' ', text).strip()

    return text

def extract_zstd(filepath,condition=None):
    """
    Processes a JSON stream from a compressed file and yields objects based on condition.

    Args:
        filepath (str): Path to the compressed JSON file
        condition (callable): Function to evaluate each object; if None, all objects are yielded

    Yields:
        dict: Each JSON object that meets the condition
    """
    with open(filepath, 'rb') as compressed_file:
        dctx = zstd.ZstdDecompressor(max_window_size=2147483648)
        with dctx.stream_reader(compressed_file) as stream_reader:
            # Read all content into a buffer
            text_content = io.TextIOWrapper(stream_reader.read(), encoding='utf-8').text
            for line in text_content.splitlines():
                obj = json.loads(line)
                if condition is None or condition(obj):
                    yield obj


def unpack_zst(in_filepath,out_filepath):
    dctx = zstd.ZstdDecompressor(max_window_size=2147483648)
    with open(in_filepath, 'rb') as ifh, open(out_filepath, 'wb') as ofh:     
        dctx.copy_stream(ifh, ofh,write_size=2**16)