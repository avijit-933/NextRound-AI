/* =========================================================
   NEXTROUND AI — API client
   Talks to the FastAPI backend (see /backend in the project).
   Change API_BASE_URL if your backend runs somewhere other
   than http://localhost:8000.
========================================================= */

const API_BASE_URL = window.NR_API_BASE_URL || 'http://localhost:8000';

/* ---------- token storage ---------- */
const Auth = {
  getAccessToken(){ return localStorage.getItem('nr-access-token'); },
  getRefreshToken(){ return localStorage.getItem('nr-refresh-token'); },
  getUser(){
    const raw = localStorage.getItem('nr-user');
    return raw ? JSON.parse(raw) : null;
  },
  setSession(tokenResponse){
    localStorage.setItem('nr-access-token', tokenResponse.access_token);
    localStorage.setItem('nr-refresh-token', tokenResponse.refresh_token);
    localStorage.setItem('nr-user', JSON.stringify(tokenResponse.user));
  },
  clearSession(){
    localStorage.removeItem('nr-access-token');
    localStorage.removeItem('nr-refresh-token');
    localStorage.removeItem('nr-user');
  },
  isLoggedIn(){ return !!this.getAccessToken(); }
};

/**
 * Human-readable message for the most common reasons fetch() itself throws
 * (as opposed to the backend returning a JSON error body).
 */
function friendlyNetworkError(err){
  if (err instanceof TypeError) {
    return `Could not reach the server at ${API_BASE_URL}. Check that the backend ` +
           `is running (uvicorn) and that this page isn't open as a local file:// ` +
           `URL (serve it over http:// instead).`;
  }
  return err.message || 'Something went wrong. Please try again.';
}

/**
 * Core request helper. Adds the Bearer token automatically, parses JSON,
 * throws a normal Error with a readable message on any failure, and
 * transparently retries once after a token refresh on a 401.
 */
async function apiRequest(path, { method = 'GET', body, isForm = false, auth = true, _retried = false } = {}) {
  const headers = {};
  if (!isForm) headers['Content-Type'] = 'application/json';
  if (auth && Auth.getAccessToken()) headers['Authorization'] = `Bearer ${Auth.getAccessToken()}`;

  let response;
  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      method,
      headers,
      body: isForm ? body : (body ? JSON.stringify(body) : undefined),
    });
  } catch (err) {
    throw new Error(friendlyNetworkError(err));
  }

  // Access token expired — try a silent refresh once, then retry the request.
  if (response.status === 401 && auth && !_retried && Auth.getRefreshToken()) {
    const refreshed = await tryRefreshToken();
    if (refreshed) {
      return apiRequest(path, { method, body, isForm, auth, _retried: true });
    }
    Auth.clearSession();
    window.location.href = 'login.html';
    throw new Error('Your session expired. Please log in again.');
  }

  if (!response.ok) {
    let detail = `Request failed (${response.status})`;
    try {
      const errBody = await response.json();
      detail = errBody.detail || JSON.stringify(errBody);
    } catch { /* response wasn't JSON */ }
    throw new Error(detail);
  }

  if (response.status === 204) return null;
  const contentType = response.headers.get('content-type') || '';
  return contentType.includes('application/json') ? response.json() : response;
}

async function tryRefreshToken(){
  try {
    const qs = new URLSearchParams({ refresh_token: Auth.getRefreshToken() });
    const res = await fetch(`${API_BASE_URL}/api/auth/refresh?${qs}`, { method: 'POST' });
    if (!res.ok) return false;
    const data = await res.json();
    Auth.setSession(data);
    return true;
  } catch {
    return false;
  }
}

/* ---------- typed API surface ---------- */
const AuthAPI = {
  register(payload){ return apiRequest('/api/auth/register', { method: 'POST', body: payload, auth: false }); },
  login(payload){ return apiRequest('/api/auth/login', { method: 'POST', body: payload, auth: false }); },
};

const UsersAPI = {
  me(){ return apiRequest('/api/users/me'); },
  getProfile(){ return apiRequest('/api/users/me/profile'); },
  updateProfile(payload){ return apiRequest('/api/users/me/profile', { method: 'PUT', body: payload }); },
  uploadProfilePicture(file){
    const form = new FormData();
    form.append('file', file);
    return apiRequest('/api/users/me/profile-picture', { method: 'POST', body: form, isForm: true });
  },
  // Public, unauthenticated — powers the landing-page testimonials section.
  recentCandidates(limit = 3){ return apiRequest(`/api/users/recent-candidates?limit=${limit}`, { auth: false }); },
};

const ResumeAPI = {
  upload(file){
    const form = new FormData();
    form.append('file', file);
    return apiRequest('/api/resume/upload', { method: 'POST', body: form, isForm: true });
  },
  active(){ return apiRequest('/api/resume/active'); },
};

const InterviewAPI = {
  create(payload){ return apiRequest('/api/interview/', { method: 'POST', body: payload }); },
  questions(id){ return apiRequest(`/api/interview/${id}/questions`); },
  submitAnswer(id, payload){ return apiRequest(`/api/interview/${id}/answer`, { method: 'POST', body: payload }); },
  submitAnswerAudio(id, questionId, audioBlob){
    const form = new FormData();
    form.append('audio', audioBlob, 'answer.webm');
    return apiRequest(`/api/interview/${id}/answer-audio?question_id=${questionId}`, { method: 'POST', body: form, isForm: true });
  },
  visionFrame(id, imageBase64, timestampSeconds){
    return apiRequest(`/api/interview/${id}/vision-frame`, { method: 'POST', body: { image_base64: imageBase64, timestamp_seconds: timestampSeconds } });
  },
  emotionFrame(id, imageBase64, timestampSeconds){
    return apiRequest(`/api/interview/${id}/emotion-frame`, { method: 'POST', body: { image_base64: imageBase64, timestamp_seconds: timestampSeconds } });
  },
  complete(id){ return apiRequest(`/api/interview/${id}/complete`, { method: 'POST' }); },
};

const ReportsAPI = {
  history(){ return apiRequest('/api/history'); },
  result(id){ return apiRequest(`/api/interview/${id}/result`); },
  detail(id){ return apiRequest(`/api/interview/${id}/detail`); },
  generateReport(id){ return apiRequest(`/api/interview/${id}/report`, { method: 'POST' }); },
  downloadUrl(id){ return `${API_BASE_URL}/api/interview/${id}/report/download`; },
  async downloadBlob(id){
    const res = await fetch(`${API_BASE_URL}/api/interview/${id}/report/download`, {
      headers: { 'Authorization': `Bearer ${Auth.getAccessToken()}` },
    });
    if (!res.ok) {
      let detail = `Download failed (${res.status})`;
      try { detail = (await res.json()).detail || detail; } catch { /* not JSON */ }
      throw new Error(detail);
    }
    return res.blob();
  },
};

const ContactAPI = {
  send(payload){ return apiRequest('/api/contact', { method: 'POST', body: payload, auth: false }); },
};

const AdminAPI = {
  stats(){ return apiRequest('/api/admin/stats'); },
  users(){ return apiRequest('/api/admin/users'); },
  reports(){ return apiRequest('/api/admin/reports'); },
  activateUser(id){ return apiRequest(`/api/admin/users/${id}/activate`, { method: 'PATCH' }); },
  deactivateUser(id){ return apiRequest(`/api/admin/users/${id}/deactivate`, { method: 'PATCH' }); },
};
