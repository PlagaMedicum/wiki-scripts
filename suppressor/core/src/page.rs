use chrono::{DateTime, Utc};

#[derive(Clone, Debug)]
pub struct PageMetadata {
    pub pageid: Option<u64>,
    pub lastrevid: Option<u64>,
    pub timestamp: Option<DateTime<Utc>>,
}

#[derive(Clone, Debug)]
pub struct PageContent {
    pub metadata: PageMetadata,
    pub content: String,
}
