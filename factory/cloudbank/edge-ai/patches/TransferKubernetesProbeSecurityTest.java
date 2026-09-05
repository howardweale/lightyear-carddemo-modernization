// Copyright (c) 2026, Oracle and/or its affiliates.
// Licensed under the Universal Permissive License v 1.0.

package com.example.transfer;

import com.example.qualification.AbstractKubernetesProbeSecurityTest;
import com.example.transfer.config.TransferOAuthSecurityConfiguration;
import org.springframework.http.HttpMethod;

class TransferKubernetesProbeSecurityTest extends AbstractKubernetesProbeSecurityTest {
    @Override
    protected Class<?> securityConfiguration() {
        return TransferOAuthSecurityConfiguration.class;
    }

    @Override
    protected String businessPath() {
        return "/transfer";
    }

    @Override
    protected HttpMethod businessMethod() {
        return HttpMethod.POST;
    }

    @Override
    protected String requiredScope() {
        return "cloudbank.transfer";
    }

}
