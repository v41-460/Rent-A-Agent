"use client";

import { useEffect, useState } from "react";
import { api, type User } from "./api";

/** undefined while loading, null when logged out. */
export function useUser(): User | null | undefined {
  const [user, setUser] = useState<User | null | undefined>(undefined);
  useEffect(() => {
    let live = true;
    api
      .me()
      .then((r) => live && setUser(r.user))
      .catch(() => live && setUser(null));
    return () => {
      live = false;
    };
  }, []);
  return user;
}
