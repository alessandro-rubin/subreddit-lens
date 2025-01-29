import pandas as pd
import zstandard as zstd
import io
import json 
import re



def preprocess(text):
    ''' applies basic preprocessing to reddit comments, removes links, markdown, quotes'''
    # Matches any string that starts with '[' and ends with ']' followed by '(', any non-space character, and ')'
    url_pattern = r'\[(.+?)\]\(.*?\S.*?\)'
    # Replaces any matches with the captured text between the square brackets
    text = re.sub(url_pattern, r'\1', text)
    #should remove quotes: anythong between > and \n\n
    quote_pattern= r'\>(.+?)\\n\\n'
    text=re.sub(quote_pattern,'',text)
    #remove \n
    text=text.replace('\\n', ' ').replace('\n', ' ').replace('\t',' ').replace('\\', ' ').replace('&gt;','').strip()
    return text

def extract_zstd(filepath,func=None):
    '''scans a zstd archive to find comments according to a certain condition
    and puts them in a pandas dataframe
    TODO: generalize condition
    func: a function applied to a json entry. if it returns true, appends the object'''
    i=0

    with open(filepath, 'rb') as compressed_file:
        dctx = zstd.ZstdDecompressor(max_window_size=2147483648)
        with  dctx.stream_reader(compressed_file) as stream_reader:
            text_stream = io.TextIOWrapper(stream_reader, encoding='utf-8')
            for line in text_stream:
                obj = json.loads(line)
                if func is not None:
                    condition=func(obj)
                else:
                    condition=True
                if condition:
                    i=i+1
                    #print(obj)
                    if i%1000==0:
                        print (i, ' comments collected.')
                    yield obj


def unpack_zst(in_filepath,out_filepath):
    dctx = zstd.ZstdDecompressor(max_window_size=2147483648)
    with open(in_filepath, 'rb') as ifh, open(out_filepath, 'wb') as ofh:     
        dctx.copy_stream(ifh, ofh,write_size=2**16)