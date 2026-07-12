export interface User {
  id: string;
  email: string;
  fullName: string;
  isEmailVerified: boolean;
}

export interface SignupPayload {
  fullName: string;
  email: string;
  password: string;
}

export interface LoginPayload {
  email: string;
  password: string;
}
