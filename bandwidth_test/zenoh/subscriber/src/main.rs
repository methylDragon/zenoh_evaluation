use bigdata::*;
use futures::prelude::*;
use futures::select;
use std::convert::TryInto;
use std::time::{Duration, SystemTime, UNIX_EPOCH};
use zenoh::*;

#[async_std::main]
async fn main() {
    env_logger::init();

    let zenoh = Zenoh::new(Properties::default().into()).await.unwrap();

    let workspace = zenoh.workspace(None).await.unwrap();

    let mut change_stream = workspace
        .subscribe(&String::from("/amazon").try_into().unwrap())
        .await
        .unwrap();

    println!("Received at,Transmission time (s),Transmitted (Bytes),Rate (B/s)");
    loop {
        select!(
            change = change_stream.next().fuse() => {
                let change = change.unwrap();
                let kind = change.kind;
                match kind {
                    ChangeKind::Put | ChangeKind::Patch => {
                        let buf = match change.value.unwrap() {
                            Value::Custom {encoding_descr: _, data: buf} => Some(buf),
                            _ => None,
                        }.unwrap();
                        let transmission_size = buf.len();
                        let big_d = deserialize_big_data(buf.contiguous().as_slice()).unwrap();
                        let transmission_finish_st = SystemTime::now();
                        let big_data::Timestamp { sec: data_ts_sec, nanosec: data_ts_nanosec } = big_d.timestamp.unwrap();
                        let transmission_start = Duration::new(data_ts_sec, data_ts_nanosec);
                        let transmission_finish = transmission_finish_st
                            .duration_since(UNIX_EPOCH)
                            .expect("System time went backwards");
                        let transmission_time = transmission_finish - transmission_start;
                        let transmission_rate: f64 =
                            transmission_size as f64 / transmission_time.as_secs_f64();
                        println!(
                            "{}.{:09},{:?},{},{}",
                            transmission_finish.as_secs(),
                            transmission_finish.subsec_nanos(),
                            transmission_time,
                            transmission_size,
                            transmission_rate);
                     },
                    ChangeKind::Delete => {
                        println!("Received {:?} for {} with timestamp {}",
                            kind, change.path, change.timestamp);
                    },
                };
            }
        )
    }
}