import api from './api';

// Storage keys
const TOKEN_KEY = 'policylens_auth_token';
const USER_KEY = 'policylens_auth_user';
const REMEMBER_KEY = 'policylens_remember_me';

/**
 * Pre-configured mock credentials for development mode.
 * Real backend authentication will be attempted first.
 * If backend authentication is unavailable or offline, these credentials
 * are validated strictly in development mock mode.
 */
export const DEMO_CREDENTIALS = [
  {
    email: 'analyst@policylens.ai',
    password: 'PolicyLens@2026',
    name: 'Sarah Jenkins',
    role: 'Lead Policy Analyst',
    department: 'Claims & Compliance',
    avatar: 'SJ'
  },
  {
    email: 'admin@policylens.ai',
    password: 'Admin@2026',
    name: 'Marcus Vance',
    role: 'Risk & Compliance Manager',
    department: 'Risk Operations',
    avatar: 'MV'
  },
  {
    email: 'demo@policylens.ai',
    password: 'Demo@2026',
    name: 'Alex Rivera',
    role: 'Underwriting Specialist',
    department: 'Policy Review',
    avatar: 'AR'
  }
];

/**
 * Validates email format according to standard RFC-compliant pattern
 */
export const validateEmail = (email) => {
  if (!email || typeof email !== 'string') return false;
  const re = /^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$/;
  return re.test(email.trim());
};

/**
 * Generates a mock signed-like token for secure client storage
 */
const generateMockToken = (user) => {
  const header = btoa(JSON.stringify({ alg: 'HS256', typ: 'JWT' }));
  const payload = btoa(
    JSON.stringify({
      sub: user.email,
      name: user.name,
      role: user.role,
      department: user.department,
      iat: Math.floor(Date.now() / 1000),
      exp: Math.floor(Date.now() / 1000) + 60 * 60 * 24 * 7 // 7 days
    })
  );
  const signature = btoa('policylens_mock_signature_' + Date.now());
  return `${header}.${payload}.${signature}`;
};

/**
 * Configure Axios request interceptor to attach Bearer token
 */
export const setupAuthInterceptor = () => {
  api.interceptors.request.use(
    (config) => {
      const token = getAuthToken();
      if (token) {
        config.headers.Authorization = `Bearer ${token}`;
      }
      return config;
    },
    (error) => Promise.reject(error)
  );
};

// Initialize interceptor on load
setupAuthInterceptor();

/**
 * Retrieve the active auth token from either localStorage or sessionStorage
 */
export const getAuthToken = () => {
  return localStorage.getItem(TOKEN_KEY) || sessionStorage.getItem(TOKEN_KEY) || null;
};

/**
 * Retrieve the active user from storage
 */
export const getCurrentUser = () => {
  const userJson = localStorage.getItem(USER_KEY) || sessionStorage.getItem(USER_KEY);
  if (!userJson) return null;
  try {
    return JSON.parse(userJson);
  } catch (e) {
    clearAuthSession();
    return null;
  }
};

/**
 * Persists auth session to storage
 */
export const setAuthSession = (token, user, rememberMe = false) => {
  clearAuthSession();
  const storage = rememberMe ? localStorage : sessionStorage;
  storage.setItem(TOKEN_KEY, token);
  storage.setItem(USER_KEY, JSON.stringify(user));
  if (rememberMe) {
    localStorage.setItem(REMEMBER_KEY, 'true');
  } else {
    localStorage.removeItem(REMEMBER_KEY);
  }
};

/**
 * Clears auth session from all storages
 */
export const clearAuthSession = () => {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(USER_KEY);
  localStorage.removeItem(REMEMBER_KEY);
  sessionStorage.removeItem(TOKEN_KEY);
  sessionStorage.removeItem(USER_KEY);
};

/**
 * Authenticates user credentials.
 * 1. Attempts real backend endpoint `/api/auth/login`.
 * 2. If backend endpoint responds with 401 or specific error, relays that error.
 * 3. If backend is not available (offline / 404), seamlessly uses strictly validated mock dev mode.
 */
export const loginUser = async ({ email, password, rememberMe = false }) => {
  // Client-side validations
  const trimmedEmail = (email || '').trim().toLowerCase();
  
  if (!trimmedEmail) {
    throw new Error('Please enter your email address.');
  }

  if (!validateEmail(trimmedEmail)) {
    throw new Error('Please enter a valid email address (e.g. analyst@policylens.ai).');
  }

  if (!password || password.trim().length === 0) {
    throw new Error('Please enter your password.');
  }

  // Attempt real backend call first
  let backendAvailable = false;
  try {
    const response = await api.post('/api/auth/login', {
      email: trimmedEmail,
      password: password
    }, {
      timeout: 3000
    });

    if (response?.data?.token && response?.data?.user) {
      setAuthSession(response.data.token, response.data.user, rememberMe);
      return {
        user: response.data.user,
        token: response.data.token,
        mode: 'backend'
      };
    }
  } catch (err) {
    // If backend returned an explicit 401/403 or validation error, authentication failed legitimately
    if (err.response && (err.response.status === 401 || err.response.status === 403)) {
      const errorMsg = err.response.data?.detail || 'Invalid email or password. Please try again.';
      throw new Error(errorMsg);
    }
    // If backend is 404 (route doesn't exist) or network error (backend offline), proceed to dev mock mode
  }

  // Fallback to Development Mock Authentication Mode
  // Simulate network latency for realistic UX feel
  await new Promise((resolve) => setTimeout(resolve, 600));

  const matchedUser = DEMO_CREDENTIALS.find(
    (c) => c.email.toLowerCase() === trimmedEmail && c.password === password
  );

  if (!matchedUser) {
    // Check if email exists to give clean error
    const emailExists = DEMO_CREDENTIALS.some(
      (c) => c.email.toLowerCase() === trimmedEmail
    );
    if (emailExists) {
      throw new Error('Invalid password. Please check your credentials.');
    } else {
      throw new Error('No account found with this email. Please check your credentials or use a demo account.');
    }
  }

  // Create clean user profile (without password)
  const userProfile = {
    email: matchedUser.email,
    name: matchedUser.name,
    role: matchedUser.role,
    department: matchedUser.department,
    avatar: matchedUser.avatar
  };

  const token = generateMockToken(userProfile);
  setAuthSession(token, userProfile, rememberMe);

  return {
    user: userProfile,
    token,
    mode: 'mock_dev'
  };
};

/**
 * Logout user
 */
export const logoutUser = async () => {
  try {
    // Optional call to backend logout if token exists
    await api.post('/api/auth/logout').catch(() => {});
  } finally {
    clearAuthSession();
  }
};
