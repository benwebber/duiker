use xdg;


const PACKAGE: &'static str = env!("CARGO_PKG_NAME");


pub fn get_database_url() -> String {
    let xdg_dirs = xdg::BaseDirectories::with_prefix(PACKAGE).unwrap();
    let database_path = xdg_dirs.place_data_file("duiker.db")
        .expect("cannot create Duiker data directory");
    return database_path.to_str().unwrap().to_owned();
}
