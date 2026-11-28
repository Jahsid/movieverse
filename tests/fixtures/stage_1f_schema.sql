CREATE TABLE ingestion_jobs (
	id SERIAL NOT NULL,
	filename VARCHAR NOT NULL,
	status VARCHAR NOT NULL,
	total_records INTEGER,
	imported_records INTEGER,
	rejected_records INTEGER,
	created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT now(),
	PRIMARY KEY (id)
);

CREATE INDEX ix_ingestion_jobs_id ON ingestion_jobs (id);

CREATE TABLE movies (
	movie_id SERIAL NOT NULL,
	title VARCHAR NOT NULL,
	genres VARCHAR,
	release_year INTEGER,
	PRIMARY KEY (movie_id)
);

CREATE INDEX ix_movies_movie_id ON movies (movie_id);

CREATE TABLE users (
	user_id SERIAL NOT NULL,
	username VARCHAR,
	created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT now(),
	PRIMARY KEY (user_id)
);

CREATE TABLE ratings (
	user_id INTEGER NOT NULL,
	movie_id INTEGER NOT NULL,
	rating FLOAT NOT NULL,
	timestamp INTEGER,
	PRIMARY KEY (user_id, movie_id),
	FOREIGN KEY(user_id) REFERENCES users (user_id),
	FOREIGN KEY(movie_id) REFERENCES movies (movie_id)
);

CREATE TABLE watchlist (
	id SERIAL NOT NULL,
	user_id INTEGER NOT NULL,
	movie_id INTEGER NOT NULL,
	status VARCHAR DEFAULT 'PLANNED' NOT NULL,
	added_at TIMESTAMP WITHOUT TIME ZONE DEFAULT now(),
	updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT now() NOT NULL,
	PRIMARY KEY (id),
	CONSTRAINT unique_user_movie UNIQUE (user_id, movie_id),
	FOREIGN KEY(user_id) REFERENCES users (user_id),
	FOREIGN KEY(movie_id) REFERENCES movies (movie_id)
);

CREATE INDEX ix_watchlist_id ON watchlist (id);
