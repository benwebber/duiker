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


const MAGIC: &'static str = r#"__duiker_import() {
    local _histignore=$HISTIGNORE
    local _histtimeformat=$HISTTIMEFORMAT
    HISTIGNORE='history*'
    HISTTIMEFORMAT='%s '
    history 1 | ./target/debug/duiker import --quiet -
    HISTIGNORE=$_histignore
    HISTTIMEFORMAT=$_histtimeformat
}"#;


pub fn head(connection: &SqliteConnection, n: i64) -> Result<Vec<models::History>, Error> {
    use schema::history::dsl::*;
    let commands = history.order(timestamp.asc()).limit(n);
    Ok(commands.load::<models::History>(connection)?)
}


fn parse_history_line(line: &str) -> Result<models::NewCommand, Error> {
    lazy_static! {
        static ref RE: Regex = Regex::new(r"^\s*?(\d+\s+)(?P<timestamp>\d+)?\s+(?P<command>.*)").unwrap();
    }
    match RE.is_match(line) {
        true => {
            let caps = RE.captures(line).unwrap();
            let timestamp = caps.name("timestamp").unwrap().as_str().parse::<i32>().unwrap();
            let command = caps.name("command").unwrap().as_str().trim();
            Ok(models::NewCommand{timestamp: timestamp, command: &command})
        }
        _ => Err(Error::InvalidHistoryLine)
    }
}


pub fn import<'a>(connection: &SqliteConnection, reader: Box<BufRead + 'a>) -> Result<usize, Error> {
    use schema::history;
    let mut n: usize = 0;
    for line in reader.lines() {
        let buf = line?;
        let command = parse_history_line(&buf)?;
        n += diesel::insert(&command).into(history::table).execute(connection)?;
    }
    Ok(n)
}


pub fn log(connection: &SqliteConnection) -> Result<Vec<models::History>, Error> {
    use schema::history::dsl::*;
    Ok(history.load::<models::History>(connection)?)
}


pub fn magic() {
    println!("{}", MAGIC);
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
