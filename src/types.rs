use std::fmt;
use std::io;
use std::error;

use diesel::result::Error as DieselError;


#[derive(Debug)]
pub enum Error {
    InvalidHistoryLine,
    Database(DieselError),
    IO(io::Error),
}


impl fmt::Display for Error {
    fn fmt(&self, f: &mut fmt::Formatter) -> fmt::Result {
        match *self {
            Error::InvalidHistoryLine => f.write_str("InvalidHistoryLine"),
            Error::Database(ref err) => err.fmt(f),
            Error::IO(ref err) => err.fmt(f),
        }
    }
}


impl error::Error for Error {
    fn description(&self) -> &str {
        match *self {
            Error::InvalidHistoryLine => "Invalid history line",
            Error::Database(ref err) => err.description(),
            Error::IO(ref err) => err.description(),
        }
    }
}


impl From<io::Error> for Error {  
    fn from(err: io::Error) -> Self {
        Error::IO(err)
    }
}


impl From<DieselError> for Error {
    fn from(err: DieselError) -> Self {
        Error::Database(err)
    }
}
