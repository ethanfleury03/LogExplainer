import { User, UserRole } from './types';

// In production, this would read from portal's session/JWT
// For now, we implement dev bypass
export function getCurrentUser(): User | null {
  if (typeof window === 'undefined') {
    // Server-side: check for session cookie/JWT
    // TODO: Wire to portal's auth system
    return null;
  }

  // Dev bypass
  const devBypass = process.env.NEXT_PUBLIC_DEV_AUTH_BYPASS === 'true';
  const isProduction = process.env.NODE_ENV === 'production';
  
  // In dev mode, always return a default user to prevent blank sidebars
  if (!isProduction) {
    // Check for role override in query param
    const params = new URLSearchParams(window.location.search);
    const roleOverride = params.get('as') as UserRole | null;
    const role: UserRole = 
      roleOverride && ['ADMIN', 'TECHNICIAN', 'CUSTOMER'].includes(roleOverride)
        ? roleOverride
        : 'TECHNICIAN'; // Default to TECHNICIAN for dev

    return {
      id: 'dev-user',
      email: 'dev@example.com',
      name: 'Dev User',
      role,
    };
  }

  // Production: read from session/JWT
  // TODO: Implement portal auth integration
  return null;
}

export function hasRole(user: User | null, requiredRole: UserRole): boolean {
  if (!user) return false;
  
  const roleHierarchy: Record<UserRole, number> = {
    CUSTOMER: 1,
    TECHNICIAN: 2,
    ADMIN: 3,
  };

  return roleHierarchy[user.role] >= roleHierarchy[requiredRole];
}

export function requireRole(user: User | null, requiredRole: UserRole): boolean {
  return hasRole(user, requiredRole);
}

