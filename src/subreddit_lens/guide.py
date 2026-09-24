"""Usage guide for people and AI assistants.

The same text is printed by 'subreddit-lens guide' and sent as the
instructions of the MCP server, so an assistant knows how to explore the data
without reading the source code.
"""

GUIDE = """\
# subreddit-lens: exploring a subreddit's data

The data is one subreddit's comments (and optionally submissions) from a
Pushshift/Arctic Shift archive, already ingested to Parquet. All times are
local to the configured timezone. Usernames such as '[deleted]' and
'AutoModerator' are excluded from per-user results (see excluded_authors).

## Start here

1. summary: size, time span, busiest hour/weekday, top commenters, and which
   optional data exists (submissions, network metrics).
2. Use a ready-made analysis if one fits the question:
   - top_users(by=comments|submissions|threads|score|replies_received|
     replies_sent|pagerank, n)
   - user_profile(author): activity, busiest hours/weekdays, who they reply
     to and who replies to them, latest comments, network metrics
   - activity(by=hour|weekday|day|month, author=None)
   - top_threads(by=comments|authors|recent, n) and thread(thread_id) for
     the full conversation in reading order (depth = nesting level)
   - search(text, author=None, n): case-insensitive substring search
   - interactions(author=None, n): strongest "A replied to B" pairs
3. Otherwise write SQL (DuckDB dialect, SELECT only, one statement) against
   these views; call schema first to see their columns:
   - comments(id, parent_id, link_id, author, body, created_utc, score,
     subreddit, is_submitter, ..., thread_id, created_at)
   - submissions(id, author, title, selftext, created_utc, score,
     num_comments, ..., created_at)  [only if submissions were ingested]
   - replies(comment_id, thread_id, author, created_at, parent_kind,
     parent_author): one row per comment whose parent author is known
   - users(author, n_comments, n_submissions, n_threads, total_score,
     first_seen, last_seen, replies_received, replies_sent)
   - threads(thread_id, title, submitter, n_comments, n_authors,
     first_comment, last_comment)
   - user_metrics(author, pagerank, hindex, community, reciprocity, ...)
     [only if the metrics step was run]
   - excluded_authors(author)

## Conventions

- comments.id has no prefix; parent_id and link_id keep Reddit's prefix:
  't1_<id>' = reply to a comment, 't3_<id>' = top-level reply to the post.
  thread_id is link_id without 't3_'. Join a reply to its parent comment
  with parent_id = 't1_' || id.
- created_at is a local timestamp; created_utc is Unix seconds (UTC).
- Comment bodies are truncated in ready-made results (max_chars); use SQL
  for full text. Results are capped (default 1000 rows for SQL).
- PageRank ranks users who receive replies from users who themselves
  receive many replies.
- Community numbers come from Louvain detection: 0 is the largest group.

## Example SQL

    -- Monthly comments and active users
    SELECT date_trunc('month', created_at) AS month,
           count(*) AS comments, count(DISTINCT author) AS authors
    FROM comments GROUP BY 1 ORDER BY 1;

    -- Who replies most to a given user
    SELECT author, count(*) AS n FROM replies
    WHERE parent_author = 'someone' AND author <> parent_author
    GROUP BY 1 ORDER BY 2 DESC LIMIT 10;

    -- Highest-scoring comments containing a word
    SELECT author, score, body FROM comments
    WHERE contains(lower(body), 'avvocato') ORDER BY score DESC LIMIT 10;

## Privacy

Usernames are pseudonymous personal data. Report aggregates where possible
and do not republish comment text at scale.
"""
