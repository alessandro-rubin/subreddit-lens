import os
import sys
import zstandard





def preprocess(text):
    ''' applies basic preprocessing, removes links, markdown, quotes'''
    import re
    # Matches any string that starts with '[' and ends with ']' followed by '(', any non-space character, and ')'
    url_pattern = r'\[(.+?)\]\(.*?\S.*?\)'
    # Replaces any matches with the captured text between the square brackets
    text = re.sub(url_pattern, r'\1', text)
    #should remove quotes: anythong between > and \n\n
    quote_pattern= r'\>(.+?)\\n\\n'
    text=re.sub(quote_pattern,'',text)
    #remove \n
    text=text.replace('\\n', ' ').replace('\n', ' ').replace('\t',' ').replace('\\', ' ')
    return text

def extract_zstd(filepath,func):
    '''scans a zstd archive to find comments according to a certain condition
    and puts them in a pandas dataframe
    TODO: generalize condition
    func: a function applied to a json entry. if it returns true, appends the object'''
    import pandas as pd
    import zstandard as zstd
    import io
    import json 

    obj_list=[]
    with open(filepath, 'rb') as fh:
        dctx = zstd.ZstdDecompressor(max_window_size=2147483648)
        stream_reader = dctx.stream_reader(fh)
        text_stream = io.TextIOWrapper(stream_reader, encoding='utf-8')
        for line in text_stream:
            # HANDLE OBJECT LOGIC HERE
            obj = json.loads(line)
            condition=func(obj)
            if condition:
                i=i+1
                #print(obj)
                obj_list.append(obj)
                if i%1000==0:
                    print (i, ' comments collected.')
        df = pd.DataFrame(obj_list)
    return df