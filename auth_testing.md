# Auth testing
1. mongosh test_database: db.users.findOne({role:"admin"}) -> password_hash starts with $2b$; indexes users.email unique, login_attempts.identifier.
2. curl -c c.txt -X POST $API/api/auth/login -H 'Content-Type: application/json' -d '{"email":"admin@chlewnia.pl","password":"Wentylacja!2026"}'; curl -b c.txt $API/api/auth/me
3. Unauthenticated access to every /api/* data/control endpoint must return 401; viewer gets 403 on commands/thresholds; operator 403 on /api/broker, /api/simulator/toggle, /api/users.
4. 5 bad logins for same email+ip -> 429 for 15 min.
