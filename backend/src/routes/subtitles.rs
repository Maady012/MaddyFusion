use std::sync::Arc;
use axum::{
    extract::{Path, State},
    response::{IntoResponse, Json},
};
use serde_json::{json, Value};
use tracing::warn;

use crate::state::AppState;

/// GET /subtitles/{media_type}/{video_id}.json
pub async fn public_subtitles(
    State(state): State<Arc<AppState>>,
    Path((media_type, video_id)): Path<(String, String)>,
) -> impl IntoResponse {
    fetch_subtitles(&state, &media_type, &video_id).await
}

/// GET /{secret_str}/subtitles/{media_type}/{video_id}.json
pub async fn user_subtitles(
    State(state): State<Arc<AppState>>,
    Path((_secret, media_type, video_id)): Path<(String, String, String)>,
) -> impl IntoResponse {
    fetch_subtitles(&state, &media_type, &video_id).await
}

async fn fetch_subtitles(state: &AppState, media_type: &str, raw_video_id: &str) -> impl IntoResponse {
    let clean_id = raw_video_id.trim_end_matches(".json");
    let target_url = format!(
        "https://opensubtitles-v3.strem.io/subtitles/{}/{}.json",
        media_type, clean_id
    );

    match state.http.get(&target_url).timeout(std::time::Duration::from_secs(4)).send().await {
        Ok(resp) if resp.status().is_success() => {
            if let Ok(data) = resp.json::<Value>().await {
                return Json(data).into_response();
            }
        }
        Ok(resp) => {
            warn!("subtitle proxy returned status: {}", resp.status());
        }
        Err(e) => {
            warn!("subtitle proxy error: {e}");
        }
    }

    Json(json!({ "subtitles": [] })).into_response()
}
