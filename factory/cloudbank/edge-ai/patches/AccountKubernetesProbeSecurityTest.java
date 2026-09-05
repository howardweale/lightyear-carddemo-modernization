// Copyright (c) 2026, Oracle and/or its affiliates.
// Licensed under the Universal Permissive License v 1.0.

package com.example.accounts;

import com.example.accounts.config.AccountOAuthSecurityConfiguration;
import com.example.qualification.AbstractKubernetesProbeSecurityTest;
import org.springframework.http.HttpMethod;

class AccountKubernetesProbeSecurityTest extends AbstractKubernetesProbeSecurityTest {
    @Override
    protected Class<?> securityConfiguration() {
        return AccountOAuthSecurityConfiguration.class;
    }

    @Override
    protected String businessPath() {
        return "/api/v1/transfers";
    }

    @Override
    protected HttpMethod businessMethod() {
        return HttpMethod.POST;
    }

    @Override
    protected String requiredScope() {
        return "cloudbank.internal";
    }

}
