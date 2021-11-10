function __duiker_import --on-event fish_prompt
    history --show-time="%s " | grep -v 'history ' | head -n1 | duiker import --shell fish --quiet -
end