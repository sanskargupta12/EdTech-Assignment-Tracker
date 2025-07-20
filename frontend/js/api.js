const API_BASE_URL = 'http://localhost:5000/api';

// Helper function to get the JWT token
function getToken() {
    return localStorage.getItem('token');
}

// Helper function to get the user role
function getUserRole() {
    return localStorage.getItem('user_role');
}

// Helper function for authenticated API requests
async function authFetch(url, options = {}) {
    const token = getToken();
    const headers = {
        'Content-Type': 'application/json',
        ...options.headers, // Allow overriding Content-Type if needed (e.g., for file uploads)
    };
    if (token) {
        headers['Authorization'] = `Bearer ${token}`;
    }

    const response = await fetch(url, { ...options, headers });

    // Handle 401 Unauthorized globally
    if (response.status === 401 || response.status === 403) {
        alert('Session expired or access denied. Please log in again.');
        logout(); // Clear token and redirect
        return null; // Return null to indicate failure
    }

    return response;
}

// User Authentication API Calls
async function loginUser(username, password) {
    return authFetch(`${API_BASE_URL}/login`, {
        method: 'POST',
        body: JSON.stringify({ username, password })
    });
}

async function signupUser(username, password, email, role) {
    return authFetch(`${API_BASE_URL}/signup`, {
        method: 'POST',
        body: JSON.stringify({ username, password, email, role })
    });
}

function logout() {
    localStorage.removeItem('token');
    localStorage.removeItem('user_role');
    localStorage.removeItem('user_id');
    window.location.href = 'login.html';
}

// Teacher API Calls
async function createAssignment(title, description, due_date) {
    return authFetch(`${API_BASE_URL}/assignments`, {
        method: 'POST',
        body: JSON.stringify({ title, description, due_date })
    });
}

async function getTeacherAssignments() {
    return authFetch(`${API_BASE_URL}/teacher/assignments`);
}

async function getViewSubmissions(assignmentId) {
    return authFetch(`${API_BASE_URL}/assignments/${assignmentId}/submissions`);
}


// Student API Calls
async function submitAssignment(assignmentId, submission_text, file_path = null) {
    return authFetch(`${API_BASE_URL}/assignments/${assignmentId}/submit`, {
        method: 'POST',
        body: JSON.stringify({ submission_text, file_path }) // file_path is placeholder for bonus
    });
}

async function getStudentAssignments() {
    return authFetch(`${API_BASE_URL}/student/assignments`);
}

async function getMySubmissions() {
    return authFetch(`${API_BASE_URL}/student/submissions`);
}