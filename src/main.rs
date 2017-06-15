#[macro_use] extern crate clap;
extern crate chrono;
#[macro_use] extern crate diesel;
#[macro_use] extern crate diesel_codegen;
#[macro_use] extern crate lazy_static;
extern crate libsqlite3_sys;
extern crate regex;
extern crate xdg;

use chrono::{UTC, TimeZone};
use diesel::prelude::*;
use diesel::sqlite::SqliteConnection;
use clap::App;

mod commands;
mod config;
mod models;
mod schema;
mod types;

use std::env;
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


fn output_command(command: &models::History) {
    lazy_static! {
        static ref HISTTIMEFORMAT: Option<String> = match env::var("HISTTIMEFORMAT") {
            Ok(fmt) => Some(String::from(fmt.trim())),
            Err(_) => None
        };
    };
    match *HISTTIMEFORMAT {
        Some(ref fmt) => {
            let timestamp = UTC.timestamp(command.timestamp as i64, 0);
            println!("{}\t{}", timestamp.format(fmt), command.command);
        },
        None => println!("{}\t{}", command.timestamp, command.command)
    }
}


pub fn output_commands(commands: &Vec<models::History>) {
    for command in commands {
        output_command(&command);
    }
}


pub fn dispatch_command(matches: clap::ArgMatches) {
    let connection = establish_connection();
    match matches.subcommand() {
        ("head", Some(m)) => {
            let entries = value_t!(m, "entries", i64).unwrap();
            if let Ok(commands) = commands::head(&connection, entries) {
                output_commands(&commands);
            };
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
            match commands::import(&connection, reader) {
                Ok(n) => {
                    if ! quiet {
                        println!("imported {} commands", n);
                    }
                }
                Err(why) => {
                    if ! quiet {
                        println!("{}", why);
                    }
                }
            };
        }
        ("log", Some(_)) => {
            if let Ok(commands) = commands::log(&connection) {
                output_commands(&commands);
            };
        }
        ("magic", Some(_)) => {
            commands::magic();
        }
        ("search", Some(m)) => {
            let expression = m.value_of("expression").unwrap();
            if let Ok(commands) = commands::search(&connection, expression) {
                output_commands(&commands);
            };
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
            if let Ok(commands) = commands::tail(&connection, entries) {
                output_commands(&commands);
            };
        }
        ("top", Some(m)) => {
            let entries = value_t!(m, "entries", i64).unwrap();
            if let Ok(commands) = commands::top(&connection, entries) {
                for command in commands {
                    println!("\t{}\t{}", command.frequency, command.command);
                };
            };
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
