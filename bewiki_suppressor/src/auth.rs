use std::collections::HashSet;

use anyhow::{Result, bail};

use crate::config::EnvConfig;
use crate::mw_api::{ApiUserInfo, MediaWikiClient};

#[derive(Clone, Debug)]
pub struct AuthState {
    pub username: String,
    pub csrf_token: String,
    pub rights: HashSet<String>,
}

impl AuthState {
    pub fn has_required_rights(&self) -> bool {
        self.rights.contains("deleterevision") && self.rights.contains("deletelogentry")
    }

    pub fn has_high_limits(&self) -> bool {
        self.rights.contains("apihighlimits")
    }
}

pub async fn authenticate(client: &MediaWikiClient, env: &EnvConfig) -> Result<AuthState> {
    let login_token = client.get_login_token().await?;
    client
        .login(&env.bot_username, &env.bot_password, &login_token)
        .await?;
    let csrf_token = client.get_csrf_token().await?;
    let ApiUserInfo { name, rights } = client.get_userinfo().await?;
    let state = AuthState {
        username: name,
        csrf_token,
        rights: rights.into_iter().collect(),
    };
    if !state.has_required_rights() {
        bail!("Authenticated session lacks deleterevision and/or deletelogentry");
    }
    Ok(state)
}

pub async fn refresh_csrf_token(client: &MediaWikiClient) -> Result<String> {
    client.get_csrf_token().await
}
