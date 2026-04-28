mod model;
mod source;
mod store;

pub use model::{RuntimeCache, SuppressionListCache, WatchedTitleDiff};
pub(crate) use source::fetch_redirect_target;
pub use store::{
    CachePersistence, CacheRefreshMode, enrich_redirects, load_cached_snapshot, load_or_bootstrap,
    refresh_cache,
};
