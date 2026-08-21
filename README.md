# bup

backup for github repos and AWS S3 and DynamoDB

# Exclusions

Each backup type (S3, DynamoDB, GitHub) has an exclusion list: names to skip, one per line. S3 entries are bucket
names, DynamoDB entries are table names, and GitHub entries are either a repo name (`my-repo`) or `owner/my-repo`.
Exclusion lists are edited in the GUI's "Exclusions" box for each backup type.

The list syntax is deliberately simple:

- `#` starts a comment that runs to the end of the line. This works for whole-line comments and for inline
  trailing comments, e.g. `my-bucket  # too big, backed up elsewhere`.
- Blank and whitespace-only lines are ignored.
- Leading and trailing whitespace around a name is ignored, so `  my-bucket ` matches `my-bucket`.
- Names are matched exactly (no wildcards).

```
# S3 buckets to skip
logs-archive        # 2 TB, backed up by a lifecycle rule instead
scratch-bucket
```

# Security Notes

- Credentials you enter (AWS secret access key, GitHub token) are stored **unencrypted** in a local
  SQLite preferences database in your user profile. Prefer AWS profiles (`~/.aws/credentials`) over
  raw keys where possible, and treat the preferences database with the same care as a credentials file.
- GitHub authentication for clone/pull is passed to git via the process environment, so the token is
  not written into each backup's `.git/config`. Backups made by older versions of bup may still have
  a token embedded in their remote URL; bup scrubs these the next time each repo is pulled.

# Acknowledgements 

<div>Icons made by <a href="https://www.freepik.com" title="Freepik">Freepik</a> from <a href="https://www.flaticon.com/" title="Flaticon">www.flaticon.com</a></div>
