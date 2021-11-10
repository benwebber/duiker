use std::io::BufRead;
// rustc incorrectly suggests `std::os::ext::process::CommandExt`.
// <https://github.com/rust-lang/rust/issues/39175>
use std::os::unix::process::CommandExt;
use std::process::Command;
use std::str;

use diesel;
use diesel::prelude::*;
use diesel::sqlite::SqliteConnection;
use diesel::types::*;
use libsqlite3_sys;
use regex::Regex;

use models;
use types::Error;


const MAGIC_BASH: &'static str = include_str!("magic.bash");
const MAGIC_FISH: &'static str = include_str!("magic.fish");


pub fn head(connection: &SqliteConnection, n: i64) -> Result<Vec<models::History>, Error> {
    use schema::history::dsl::*;
    let commands = history.order(timestamp.asc()).limit(n);
    Ok(commands.load::<models::History>(connection)?)
}


fn parse_history_line(line: &str) -> Result<models::NewCommand, Error> {
    lazy_static! {
        static ref RE: Regex = Regex::new(r"^\s*?(\d+\s+)?(?P<timestamp>\d+)?\s+(?P<command>.*)").unwrap();
    }
    match RE.is_match(line) {
        true => {
            let caps = RE.captures(line).unwrap();
            let timestamp = caps.name("timestamp").unwrap().as_str().parse::<i32>().unwrap();
            let command = caps.name("command").unwrap().as_str().trim();
            Ok(models::NewCommand{timestamp: timestamp, command: &command})
        }
        _ => {
            println!("Invalid line {}", line);
            Err(Error::InvalidHistoryLine)
        }
    }
}


pub fn import<'a>(connection: &SqliteConnection, reader: Box<BufRead + 'a>) -> Result<usize, Error> {
    use schema::history;
    let mut n: usize = 0;
    for line in reader.lines() {
        let buf = line?;
        if buf.trim().is_empty() {
            continue;
        }
        let command = parse_history_line(&buf)?;
        n += diesel::insert(&command).into(history::table).execute(connection)?;
    }
    Ok(n)
}


pub fn log(connection: &SqliteConnection) -> Result<Vec<models::History>, Error> {
    use schema::history::dsl::*;
    Ok(history.load::<models::History>(connection)?)
}


pub fn magic(shell: &str) {
    match shell {
        "bash" => print!("{}", MAGIC_BASH),
        "fish" => print!("{}", MAGIC_FISH),
        _ => {},
    }
}


pub fn search(connection: &SqliteConnection, expression: &str) -> Result<Vec<models::History>, Error> {
    use diesel::expression::sql;
    let query = sql::<(Integer, Integer, Text)>("SELECT history.*
                                                   FROM fts_history
                                                   JOIN history
                                                     ON fts_history.history_id = history.id
                                                  WHERE fts_history MATCH ?");
    Ok(query.bind::<Text, _>(expression).load::<models::History>(connection)?)
}


pub fn sqlite3(sqlite3_options: Vec<&str>) {
    Command::new("sqlite3")
        .args(&sqlite3_options)
        .exec();
}


pub fn tail(connection: &SqliteConnection, n: i64) -> Result<Vec<models::History>, Error> {
    use schema::history::dsl::*;
    let commands = history.select(id)
        .order(timestamp.desc())
        .limit(n);
    let sorted = history.filter(id.eq_any(commands))
        .order(timestamp.asc());
    Ok(sorted.load::<models::History>(connection)?)
}


pub fn top(connection: &SqliteConnection, n: i64) -> Result<Vec<models::Frequency>, Error> {
    use diesel::expression::sql;
    let query = sql::<(Integer, Text)>("SELECT COUNT(*) AS frequency, command
                                          FROM history
                                         GROUP BY command
                                         ORDER BY frequency DESC
                                         LIMIT ?");
    Ok(query.bind::<BigInt, _>(n).load::<models::Frequency>(connection)?)
}


pub fn version(verbose: bool) {
    println!("{} {}", env!("CARGO_PKG_NAME"), env!("CARGO_PKG_VERSION"));
    if verbose {
        println!("SQLite3 {}",
                 str::from_utf8(libsqlite3_sys::SQLITE_VERSION).unwrap());
    }
}


#[cfg(test)]
mod tests {
    use super::*;
    use crate::establish_connection;

    use std::sync::Mutex;
    use lazy_static;

    lazy_static! {
        static ref CONNECTION_MUTEX: Mutex<()> = Mutex::new(());
    }

    fn get_test_connection() -> SqliteConnection {
        let connection  = establish_connection();
        connection.begin_test_transaction().unwrap();
        connection
    }

    #[test]
    fn it_should_handle_bash_import() {
        let _guard = CONNECTION_MUTEX.lock().unwrap();
        let mut input: &[u8] = "2 1636577632 some command".as_bytes();
        let connection = get_test_connection();
        let res = import(&connection, Box::new(&mut input));
        
        assert!(res.is_ok());
        assert_eq!(1, res.unwrap());
    }

    #[test]
    fn it_should_handle_fish_import() {
        let _guard = CONNECTION_MUTEX.lock().unwrap();
        let mut input: &[u8] = "1636577632 some command".as_bytes();
        let connection = get_test_connection();
        let res = import(&connection, Box::new(&mut input));

        assert!(res.is_ok());
        assert_eq!(1, res.unwrap());
    }

    #[test]
    fn it_should_handle_an_empty_line() {
        let _guard = CONNECTION_MUTEX.lock().unwrap();
        let mut input: &[u8] = "  ".as_bytes();
        let connection = get_test_connection();
        let res = import(&connection, Box::new(&mut input));

        assert!(res.is_ok());
        assert_eq!(0, res.unwrap());
    }

    #[test]
    fn it_should_handle_bad_import() {
        let _guard = CONNECTION_MUTEX.lock().unwrap();
        let mut input: &[u8] = "invalide input command".as_bytes();
        let connection = get_test_connection();
        let res = import(&connection, Box::new(&mut input));

        assert!(res.is_err());
    }
}