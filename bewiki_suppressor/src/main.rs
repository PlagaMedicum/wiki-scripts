#[tokio::main]
async fn main() -> anyhow::Result<()> {
    bewiki_suppressor::run().await
}
