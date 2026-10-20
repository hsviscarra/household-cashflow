# Views

The `mart` view definitions live in `api/migrations/views/` so the migrations (and the Docker
image) ship them. Each file is the current definition; a migration that changes a view reads it.
