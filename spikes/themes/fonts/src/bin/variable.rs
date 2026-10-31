fn main() {
    let mut db = fontdb::Database::new();
    db.load_system_fonts();
    for face in db.faces() {
        let first = &face.families[0].0;
        if first.starts_with("Sitka") || first.starts_with("Segoe UI Variable") {
            println!("{:?} ps={} index={} {:?}", face.families, face.post_script_name, face.index, face.source);
        }
    }
}
