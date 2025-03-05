$(document).ready(function () {
    $('#commentText').on('change keyup paste', function () {
        const cv = $('#commentText').val();

        if (cv.length <= 0) {
            $('#doPost').prop('disabled', true);
        } else {
            $('#doPost').prop('disabled', false);
        }
    });


    $('#cancelEditTime').click(function () {
        if (this.hasAttribute('disabled')) {
            return;
        }

        $('#timeEditCell').addClass('is-hidden');
        $('#timeValue').removeClass('is-hidden');
        $('#editTime').removeClass('is-hidden');
    });

    $('#cancelEditServer').click(function () {
        if (this.hasAttribute('disabled')) {
            return;
        }

        $('#serverEditCell').addClass('is-hidden');
        $('#serverValue').removeClass('is-hidden');
        $('#editServer').removeClass('is-hidden');
    });

    $('#cancelEditScope').click(function () {
        if (this.hasAttribute('disabled')) {
            return;
        }

        $('#scopeEditCell').addClass('is-hidden');
        $('#scopeValue').removeClass('is-hidden');
        $('#editScope').removeClass('is-hidden');
    });

    $('#cancelEditReason').click(function () {
        if (this.hasAttribute('disabled')) {
            return;
        }

        $('#reasonEditCell').addClass('is-hidden');
        $('#reasonValue').removeClass('is-hidden');
        $('#editReason').removeClass('is-hidden');
    });

    restrictionsCancel.click(function () {
        if (this.hasAttribute('disabled')) {
            return;
        }

        restrictionsEditCell.addClass('is-hidden');
        $('#restrictionsValue').removeClass('is-hidden');
        restrictionsEdit.removeClass('is-hidden');
        restrictionsCancel.addClass('is-hidden');
    });

    $('#editTimePerm').click(editTogglePerm);
    $('#editTimeTimeDec').click(editToggleTimeDec);
});


function submit_comment(infraction) {
    const text = $('#commentText').val();
    const is_private = $('#privateCheck').prop('checked');
    const target = infraction['id'];

    gbRequest('POST', '/api/infractions/' + target + '/comment', {
        'content': text,
        'set_private': is_private
    }, true).then(function (repl) {
        if (!repl.ok) {
            const errorData = repl.json();
            throw new Error(errorData.detail || defaultAPIError);
        }

        repl.json().then(function (j) {
            // Redo the comment section
            commentContainer.empty();

            addComments(mergeCommentFiles(j));

            $('#commentText').prop('disabled', false).val('');
            $('#doPost').removeClass('is-loading').blur();
            $('#privateCheck').prop('checked', false);

        }).catch(logException);
    }).catch(logException);
}

function prepareEditor(infraction) {
    // Comment field and upload buttons will not exist when permissions are insufficient

    const postComment = document.getElementById('doPost');

    if (postComment) {
        $(postComment).off('click');
        $(postComment).click(function () {
            $(postComment).addClass('is-loading');
            $('#commentText').prop('disabled', true);
            submit_comment(infraction);
        });
    }

    const attachFile = document.getElementById('doFileUpload');

    if (attachFile) {
        $(attachFile).off('change');

        $(attachFile).change(function () {
            if (attachFile.files.length > 0) {
                $('#FileButton').addClass('is-loading');
                $('#doFileUpload').prop('disabled', true);

                uploadAttachment(
                    infraction['id'],
                    attachFile.files[0].name,
                    attachFile.files[0],
                    $('#privateCheck').prop('checked')
                ).then(function () {
                    gbRequest('GET', '/api/infractions/' + infraction['id'] + '/info', null, true).then(function (r) {
                        r.json().then(function (j) {
                            commentContainer.empty();
                            addComments(mergeCommentFiles(j));
                            $('#FileButton').removeClass('is-loading');
                            $('#doFileUpload').prop('disabled', false);
                        });
                    }).catch(logException);
                }).catch(logException);
            }
        });
    }

    if (getMeta('current_user') === '') {
        return;
    }

    const current_user = parseInt(getMeta('current_user'));
    const active_perms = parseInt(getMeta('active_permissions'));

    if (
        (
            infraction.hasOwnProperty('admin')
            && infraction['admin'] === current_user
            && active_perms & PERMISSION.CREATE_INFRACTION
        )
        || active_perms & PERMISSION.EDIT_ALL_INFRACTIONS
    ) {
        prepareEdits(infraction);
    }
}

function prepareEdits(infraction) {
    $('.edit').removeClass('is-hidden').off('click');
    $('#infOptions').removeClass('is-hidden');

    if (!(infraction['flags'] & (INFRACTION.SESSION))) {
        $('#editTime').click(function () {
            editTime(infraction);
        });
    }

    $('#editServer').click(function () {
        editServer(infraction);
    });

    $('#editScope').click(function () {
        editScope(infraction);
    });

    $('#editReason').click(function () {
        editReason(infraction);
    });

    if (restrictionsCancel.hasClass('is-hidden')) {
        restrictionsEditCell.addClass('is-hidden');
        $('#restrictionsValue').removeClass('is-hidden');
        restrictionsEdit.removeClass('is-hidden');
    }

    restrictionsEdit.click(function () {
        editRestrictions(infraction);
    });

    const rem = $('#triggerRemoveVis');

    $('#triggerRemove').off('click').click(function () {
        startRemove(infraction);
    });

    const reinst = $('#triggerReinstVis');

    $('#triggerReinstate').off('click').click(function () {
        setLoading();

        const mod = {
            'set_removal_state': false
        };

        submit_edit(infraction['id'], mod).then(function (d) {
            unsetLoading();
            wrapSetupView(d);
        }).catch(function (e) {
            unsetLoading();
            logException(e);
        });
    });

    rem.addClass('is-hidden');
    reinst.addClass('is-hidden');

    if (infraction['flags'] & (INFRACTION.REMOVED)) {
        reinst.removeClass('is-hidden');
    } else {
        rem.removeClass('is-hidden');
    }
}

function editTogglePerm() {
    if (this.hasAttribute('disabled')) {
        return;
    }

    if (this.classList.contains('is-light')) {
        $(this).removeClass('is-light');
        $('#editTimeTimeDec').attr('disabled', 1).addClass('is-light');
        $('#editTimeTime').prop('disabled', true);
        $('#editTimeUnitSelect').prop('disabled', true);
    } else {
        $(this).addClass('is-light');
        $('#editTimeTimeDec').removeAttr('disabled');
        $('#editTimeTime').prop('disabled', false);
        $('#editTimeUnitSelect').prop('disabled', false);
    }
}

function editToggleTimeDec() {
    if (this.hasAttribute('disabled')) {
        return;
    }

    if (this.classList.contains('is-light')) {
        $(this).removeClass('is-light');
        $('#editTimePerm').attr('disabled', 1).addClass('is-light');
        $('#editTimeTime').prop('disabled', false);
        $('#editTimeUnitSelect').prop('disabled', false);
    } else {
        $(this).addClass('is-light');
        $('#editTimePerm').removeAttr('disabled');
    }
}

async function submit_edit(id, mod) {
    resp = await gbRequest('PATCH', '/api/infractions/' + id, mod, true);

    if (!resp.ok) {
        const errorData = await resp.json();
        throw new Error(errorData.detail || defaultAPIError);
    }

    return await resp.json();
}

function process_time_edit(infraction) {
    const tde = $('#editTimeTimeDec');
    const ett = $('#editTimeTime');
    const etp = $('#editTimePerm');
    const ets = $('#editTimeUnitSelect');

    etp.attr('disabled', 1);
    tde.attr('disabled', 1);
    ett.prop('disabled', true);
    ets.prop('disabled', true);

    const unit = ets.val();
    const mult = multipliers[unit];

    $('#cancelEditTime').attr('disabled', 1);
    $('#submitEditTime').addClass('is-loading');

    const mod = {};

    if (!tde.hasClass('is-light')) {
        mod['time_left'] = parseInt(ett.val()) * mult;
    } else if (!etp.hasClass('is-light')) {
        mod['make_permanent'] = true;
    } else {
        mod['expiration'] = parseInt(ett.val()) * mult;
    }

    submit_edit(infraction['id'], mod).then(function (new_inf) {
        wrapSetupView(new_inf, 0);
    }).catch(logException);
}

function editTime(infraction) {
    $('#timeEditCell').removeClass('is-hidden');
    $('#timeValue').addClass('is-hidden');
    $('#editTime').addClass('is-hidden');

    const perm = $('#editTimePerm');
    const td = $('#editTimeTimeDec');
    const ett = $('#editTimeTime');
    const ets = $('#editTimeUnitSelect');

    perm.removeAttr('disabled').addClass('is-light');
    td.removeAttr('disabled').addClass('is-light').removeAttr('data-disable-ban', '1');
    ett.prop('disabled', false).val('');
    ets.prop('disabled', false).val('m');
    $('#cancelEditTime').removeAttr('disabled');

    console.log(infraction);

    // Permanent
    if (infraction['flags'] & (INFRACTION.PERMANENT)) {
        perm.removeClass('is-light');
        td.attr('disabled', '1');
        ett.prop('disabled', true);
        ets.prop('disabled', true);
    } else if (infraction['flags'] & (INFRACTION.DEC_ONLINE_ONLY)) {
        perm.attr('disabled', '1');
        td.removeClass('is-light');
        ett.val(Math.ceil(infraction['orig_length'] / 60).toString());
    } else {
        ett.val(Math.ceil((infraction['expires'] - infraction['created']) / 60));
    }


    if (infraction['flags'] & (INFRACTION.BAN)) {
        td.attr('disabled', '1').attr('data-disable-ban', '1');
    }

    $('#submitEditTime').off('click').click(function () {
        process_time_edit(infraction);
    }).removeClass('is-loading');
}

function editServer(infraction) {
    $('#serverEditCell').removeClass('is-hidden');
    $('#serverValue').addClass('is-hidden');
    $('#editServer').addClass('is-hidden');

    // Load all the server names into the server box
    const ess = $('#editServerServer');
    const essub = $('#submitEditServer');
    const ces = $('#cancelEditServer');

    ces.removeAttr('disabled');
    ess.prop('disabled', false);

    ess.empty();

    // First the web option

    const web = document.createElement('option');
    web.setAttribute('value', 'web');
    $(web).text('Web');
    ess.append(web);

    // Is Web?
    if (infraction['flags'] & (INFRACTION.WEB)) {
        $(web).prop('selected', true);
    }

    for (let i = 0; i < server_data.length; i++) {
        const nd = document.createElement('option');
        nd.setAttribute('value', server_data[i]['id']);

        if (server_data[i].hasOwnProperty('friendly_name')) {
            $(nd).text(
                server_data[i]['friendly_name']
                + ' (' + server_data[i]['ip'] + ':' + server_data[i]['game_port'] + ')'
            );
        } else {
            $(nd).text(server_data[i]['ip'] + ':' + server_data[i]['game_port']);
        }

        if (!(infraction['flags'] & (INFRACTION.WEB)) && infraction['server'] === server_data[i]['id']) {
            $(nd).prop('selected', true);
        }

        ess.append(nd);
    }

    // Rig up the save button
    essub.off('click').click(function () {
        if (ess.val() && !this.hasAttribute('disabled')) {
            essub.attr('disabled', '1').addClass('is-loading');
            ces.attr('disabled', '1');
            ess.prop('disabled', true);

            process_server_edit(infraction, ess.val());
        }
    }).removeClass('is-loading').removeAttr('disabled');

}

function process_server_edit(infraction, new_val) {
    function doSuccess() {
        $('#submitEditServer').removeAttr('disabled').removeClass('is-loading');
        $('#cancelEditServer').removeAttr('disabled');
        $('#editServerServer').prop('disabled', false);
        $('#serverEditCell').addClass('is-hidden');
        $('#serverValue').removeClass('is-hidden');
        $('#editServer').removeClass('is-hidden');
    }

    // Save time if we don't actually need to update the server
    if ((new_val === 'web' && infraction['flags'] & (INFRACTION.WEB)) || new_val === infraction['server']) {
        doSuccess();
        return;
    }

    const mod = {};

    if (new_val === 'web') {
        mod['make_web'] = true;
    } else {
        mod['server'] = new_val;
    }

    submit_edit(infraction['id'], mod).then(function (j) {
        wrapSetupView(j, 0);
    }).catch(logException);
}

function editScope(infraction) {
    const ess = $('#editScopeScope');

    const ces = $('#cancelEditScope');

    ces.removeAttr('disabled');
    ess.prop('disabled', false);

    $('#scopeEditCell').removeClass('is-hidden');
    $('#scopeValue').addClass('is-hidden');
    $('#editScope').addClass('is-hidden');
    $('.oeserver').prop('selected', false);

    if (infraction['flags'] & (INFRACTION.GLOBAL)) {
        ess.val('global');
    } else {
        ess.val('server');
    }

    const essub = $('#submitEditScope');

    essub.off('click').click(function () {
        if ($(this).attr('disabled')) {
            return;
        }

        essub.attr('disabled', '1').addClass('is-loading');
        ces.attr('disabled', '1');
        ess.prop('disabled', true);

        process_scope_edit(infraction, ess.val());

    }).removeClass('is-loading').removeAttr('disabled');
}

function process_scope_edit(infraction, new_val) {
    const mod = {};

    if (new_val === 'server') {
        mod['scope'] = 'server';
    } else {
        mod['scope'] = 'global';
    }

    submit_edit(infraction['id'], mod).then(function (j) {
        wrapSetupView(j, 0);
    }).catch(logException);
}

function editReason(infraction) {
    $('#reasonEditCell').removeClass('is-hidden');
    $('#reasonValue').addClass('is-hidden');
    $('#editReason').addClass('is-hidden');

    const ess = $('#editReasonReason');
    const essub = $('#submitEditReason');
    const ces = $('#cancelEditReason');

    ess.val(infraction['reason']).prop('disabled', false);
    ces.removeAttr('disabled');

    essub.off('click').click(function () {
        if ($(this).attr('disabled')) {
            return;
        }

        essub.attr('disabled', '1').addClass('is-loading');
        ces.attr('disabled', '1');
        ess.prop('disabled', true);

        process_reason_edit(infraction, ess.val());

    }).removeClass('is-loading').removeAttr('disabled');

}

function process_reason_edit(infraction, val) {
    const mod = {
        'reason': val
    };

    submit_edit(infraction['id'], mod).then(function (j) {
        wrapSetupView(j, 0);
    }).catch(logException);
}

function editRestrictions(infraction) {
    const ic = $('#restrictionsCancelIcon');

    ic.removeClass('fa-hourglass-half').addClass('fa-undo');

    const et = $('.etag');
    et.removeClass('is-hidden').addClass('half-opacity').off('click');
    et.removeAttr('disabled');

    restrictionsEditCell.removeClass('is-hidden');
    $('#restrictionsValue').addClass('is-hidden');
    restrictionsEdit.addClass('is-hidden');
    restrictionsCancel.removeClass('is-hidden');

    if (infraction['flags'] & (INFRACTION.VOICE_BLOCK)) {
        voiceChatFlagEdit.removeClass('half-opacity');
    }

    if (infraction['flags'] & (INFRACTION.CHAT_BLOCK)) {
        textChatFlagEdit.removeClass('half-opacity');
    }

    if (infraction['flags'] & (INFRACTION.BAN)) {
        banFlagEdit.removeClass('half-opacity');
    }

    if (infraction['flags'] & (INFRACTION.ADMIN_CHAT_BLOCK)) {
        adminChatFlagEdit.removeClass('half-opacity');
    }

    if (infraction['flags'] & (INFRACTION.CALL_ADMIN_BAN)) {
        callAdminFlagEdit.removeClass('half-opacity');
    }

    if (infraction['flags'] & (INFRACTION.ITEM_BLOCK)) {
        itemFlagEdit.removeClass('half-opacity');
    }

    function handleUWU() {
        if (this.hasAttribute('disabled')) {
            return;
        }

        et.attr('disabled', '1');
        restrictionsCancel.attr('disabled', '1');
        ic.addClass('fa-hourglass-half').removeClass('fa-undo');

        if (this.classList.contains('half-opacity')) {
            this.classList.remove('half-opacity');
        } else {
            this.classList.add('half-opacity');
        }

        process_edit_restriction(infraction).then(function (d) {
            et.removeAttr('disabled');
            restrictionsCancel.removeAttr('disabled');
            ic.removeClass('fa-hourglass-half').addClass('fa-undo');

            wrapSetupView(d);

            editRestrictions(d);
        }).catch(logException);
    }

    et.click(handleUWU);
}

async function process_edit_restriction(infraction) {
    const mod = {
        'punishments': []
    };

    const et = $('.etag');

    for (let i = 0; i < et.length; i++) {
        if (!et[i].classList.contains('half-opacity')) {
            mod['punishments'].push(et[i].getAttribute('data-punishment'));
        }
    }

    return await submit_edit(infraction['id'], mod);
}

const cr = $('#cancelRemoval');

function startRemove(infraction) {
    const rm = $('#removeModal');

    rm.addClass('is-active');
    const rb = $('#removeButton');


    rb.off('click').click(function () {
        if (this.hasAttribute('disabled')) {
            return;
        }

        const reason = $('#removalReason').val();

        if (reason.length < 1 || reason.length > 240) {
            return;
        }

        cr.attr('disabled', '1');
        rb.attr('disabled', '1').addClass('is-loading');

        const mod = {
            'set_removal_state': true,
            'removal_reason': reason
        };

        submit_edit(infraction['id'], mod).then(function (d) {
            cr.removeAttr('disabled');
            rb.removeAttr('disabled').removeClass('is-loading');

            rm.removeClass('is-active');
            wrapSetupView(d);
        }).catch(function (e) {
            rm.removeClass('is-active');

            logException(e);
        });

    });
}

cr.click(function () {
    if (this.hasAttribute('disabled')) {
        return;
    }

    $('#removeModal').removeClass('is-active');
});
