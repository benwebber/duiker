__duiker_import() {
    local _histignore=$HISTIGNORE
    local _histtimeformat=$HISTTIMEFORMAT
    HISTIGNORE='history*'
    HISTTIMEFORMAT='%s '
    history 1 | duiker import --quiet -
    HISTIGNORE=$_histignore
    HISTTIMEFORMAT=$_histtimeformat
}
