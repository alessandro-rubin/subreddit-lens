"""Constants shared across subpackages."""

# Placeholder author set by Reddit for deleted accounts, and the moderation
# bot present in most subreddits. Neither is a real participant, and both
# would dominate per-user metrics as artificial hubs.
DEFAULT_EXCLUDED_AUTHORS: frozenset[str] = frozenset({"[deleted]", "AutoModerator"})

# Comment bodies set by Reddit when a user deletes or moderators remove a comment.
REMOVED_BODIES: frozenset[str] = frozenset({"[deleted]", "[removed]"})
