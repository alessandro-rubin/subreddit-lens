from pmaw import PushshiftAPI
import pandas as pd
from datetime import datetime
import pickle
import parquet
import os


after = int(datetime(2020,1,1,0,0).timestamp())
before = int(datetime(2023,12,31,23,59).timestamp())
api = PushshiftAPI()
parameters={'subreddit':'litigi', 'size':1000000,'until':before,'since':after}
gen = api.search_comments( **parameters)
print(f'Retrieved {len(gen)} comments from Pushshift')

comments=pd.DataFrame([comment for comment in gen])

comments.to_parquet("dataframe.parquet")
comments.to_pickle('my_df.pickle')
# for batch in range(batches):
#     comment=[]
#     for comment in gen:
#         if i>=max:
#             print('All ', max, ' comments retrieved.\n')
#             break
#         #print('Author: ', comment.d_['author'])
#         comments.append(comment)
#         i+=1
#         if (i%100 ==0):
#             print('Retrieved ', i, ' comments.')
#     df = pd.DataFrame([c for c in comments])
#     feature_list=['body','author','created_utc','subreddit','id','permalink']
#     df=df[feature_list]
#     print('Writing to csv...\nFeature list is:\n',feature_list)
#     df.to_csv('aa_batch',batch,'.csv',index=False)
print('Done.\n')

#print(comments[0])
#print(len(comments))

#print(df[['body','author','created_utc','subreddit','id','permalink']])
