use schema::*;

#[derive(Identifiable, Queryable)]
#[table_name = "history"]
pub struct History {
    pub id: i32,
    pub timestamp: i32,
    pub command: String,
}

#[derive(Clone, Debug, Insertable)]
#[table_name = "history"]
pub struct NewCommand<'a> {
    pub timestamp: i32,
    pub command: &'a str,
}
