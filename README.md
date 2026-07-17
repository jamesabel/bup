# bup

backup for github repos and AWS S3 and DynamoDB

# Security Notes

- Credentials you enter (AWS secret access key, GitHub token) are stored **unencrypted** in a local
  SQLite preferences database in your user profile. Prefer AWS profiles (`~/.aws/credentials`) over
  raw keys where possible, and treat the preferences database with the same care as a credentials file.
- GitHub authentication for clone/pull is passed to git via the process environment, so the token is
  not written into each backup's `.git/config`. Backups made by older versions of bup may still have
  a token embedded in their remote URL; bup scrubs these the next time each repo is pulled.

# Acknowledgements 

<div>Icons made by <a href="https://www.freepik.com" title="Freepik">Freepik</a> from <a href="https://www.flaticon.com/" title="Flaticon">www.flaticon.com</a></div>
