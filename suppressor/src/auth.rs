use std::collections::HashSet;

use anyhow::{Result, bail};

use crate::config::EnvConfig;
use crate::mw_api::{ApiUserInfo, MediaWikiClient};

const REQUIRED_RIGHTS: [&str; 3] = ["bot", "deleterevision", "deletelogentry"];

#[derive(Clone, Debug)]
pub struct AuthState {
    pub username: String,
    pub csrf_token: String,
    pub rights: HashSet<String>,
}

impl AuthState {
    pub fn missing_required_rights(&self) -> Vec<&'static str> {
        REQUIRED_RIGHTS
            .iter()
            .copied()
            .filter(|right| !self.rights.contains(*right))
            .collect()
    }

    pub fn has_required_rights(&self) -> bool {
        self.missing_required_rights().is_empty()
    }

    pub fn has_bot_right(&self) -> bool {
        self.rights.contains("bot")
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
    let missing = state.missing_required_rights();
    if !missing.is_empty() {
        bail!(
            "Authenticated session lacks required rights for bot-marked revisiondelete actions: {}",
            missing.join(", ")
        );
    }
    Ok(state)
}

pub async fn refresh_csrf_token(client: &MediaWikiClient) -> Result<String> {
    client.get_csrf_token().await
}

#[cfg(test)]
mod tests {
    use super::*;

    fn auth_state(rights: &[&str]) -> AuthState {
        AuthState {
            username: "Wizardist".to_string(),
            csrf_token: "csrf".to_string(),
            rights: rights.iter().map(|right| (*right).to_string()).collect(),
        }
    }

    #[test]
    fn reports_missing_bot_right() {
        let state = auth_state(&["deleterevision", "deletelogentry"]);
        assert_eq!(state.missing_required_rights(), vec!["bot"]);
        assert!(!state.has_required_rights());
        assert!(!state.has_bot_right());
    }

    #[test]
    fn accepts_full_required_right_set() {
        let state = auth_state(&["bot", "deleterevision", "deletelogentry"]);
        assert!(state.missing_required_rights().is_empty());
        assert!(state.has_required_rights());
        assert!(state.has_bot_right());
    }
}
