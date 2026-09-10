package com.example.common.security;

/** Local HTTP framing fixture only; no live credentials or OAuth claims. */
public class CloudBankServiceTokenProvider {
    public String getAuthorizationHeader() {
        return "Bearer synthetic";
    }
}
