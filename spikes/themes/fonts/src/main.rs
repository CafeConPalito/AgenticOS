//! Phase 22, spike S1: which font families does fontdb see on this machine, and how fast?
use std::collections::BTreeSet;
use std::time::Instant;

fn main() {
    let start = Instant::now();
    let mut db = fontdb::Database::new();
    db.load_system_fonts();
    let mut families = BTreeSet::new();
    let mut paths = BTreeSet::new();
    for face in db.faces() {
        if let Some((name, _)) = face.families.first() {
            families.insert(name.clone());
        }
        if let fontdb::Source::File(path) = &face.source {
            if let Some(dir) = path.parent() {
                paths.insert(dir.display().to_string());
            }
        }
    }
    println!("faces={} families={} elapsed_ms={}", db.len(), families.len(), start.elapsed().as_millis());
    println!("dirs={:?}", paths);
    for family in &families {
        println!("{family}");
    }
}
