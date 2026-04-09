#[tokio::main]
async fn main() -> anyhow::Result<()> {
    suppressor::run().await
}
