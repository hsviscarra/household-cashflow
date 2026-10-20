# Views

The current `mart` view definitions live in `api/migrations/views/*.sql`; the migration that last
changed them (0008) reads them from there. Older migrations read frozen copies in
`api/migrations/views/<revision>/`. When a view changes, copy the current files into a folder named
after the migration that introduced them, point that migration at the copy, then edit the current
files in a new migration.
