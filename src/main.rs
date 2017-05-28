#![feature(slice_patterns)]

#[macro_use] extern crate clap;
extern crate chrono;
#[macro_use] extern crate diesel;
#[macro_use] extern crate diesel_codegen;
#[macro_use] extern crate lazy_static;
extern crate libsqlite3_sys;
extern crate regex;
extern crate xdg;

use diesel::prelude::*;
use diesel::sqlite::SqliteConnection;
use clap::App;

mod commands;
mod config;
mod models;
mod schema;
mod types;

use std::fs::File;
use std::io;
use std::io::prelude::*;

embed_migrations!("migrations");


pub fn establish_connection() -> SqliteConnection {
    let database_url = config::get_database_url();
    let connection = SqliteConnection::establish(&database_url).unwrap();
    embedded_migrations::run(&connection).unwrap();
    connection
}


pub fn dispatch_command(matches: clap::ArgMatches) {
    let connection = establish_connection();
    match matches.subcommand() {
        ("head", Some(m)) => {
            let entries = value_t!(m, "entries", i64).unwrap();
            commands::head(&connection, entries);
        }
        ("import", Some(m)) => {
            let stdin = io::stdin();
            let reader = match m.value_of("input") {
                None => Box::new(stdin.lock()) as Box<BufRead>,
                Some(path) if path == "-" => Box::new(stdin.lock()) as Box<BufRead>,
                Some(path) => Box::new(io::BufReader::new(File::open(path).unwrap())) as Box<BufRead>,
            };
            let mut quiet = false;
            if m.is_present("quiet") {
                quiet = true;
            }
            match commands::import(&connection, reader, quiet) {
                Ok(n) => println!("imported {} commands", n),
                Err(why) => println!("{}", why),
            };
        }
        ("log", Some(_)) => {
            commands::log(&connection);
        }
        ("magic", Some(_)) => {
            commands::magic();
        }
        ("search", Some(m)) => {
            let expression = m.value_of("expression").unwrap();
            commands::search(&connection, expression);
        }
        ("sqlite3", Some(m)) => {
            let database_url = config::get_database_url();
            let mut sqlite3_options: Vec<&str> = match m.values_of("sqlite3_options") {
                Some(options) => options.collect(),
                None => clap::Values::default().collect(),
            };
            sqlite3_options.push(&database_url);
            commands::sqlite3(sqlite3_options);
        }
        ("tail", Some(m)) => {
            let entries = value_t!(m, "entries", i64).unwrap();
            commands::tail(&connection, entries);
        }
        ("version", Some(m)) => {
            let mut verbose = false;
            if m.is_present("verbose") {
                verbose = true;
            }
            commands::version(verbose);
        }
        _ => unreachable!(),
    }
}


fn main() {
    let yaml = load_yaml!("cli.yaml");
    let matches = App::from_yaml(yaml).get_matches();
    dispatch_command(matches);
}
