const viewModal = $('#infraction_view_modal');
const userAvatar = $('#avatar_img');
const userName = $('#user_name');
const createdAt = $('#createdAt');

const vpnTag = $('#fvpn');
const removedTag = $('#fremoved');
const expiredTag = $('#fexpired');
const systemTag = $('#fsystem');
const webTag = $('#fweb');

const idContainer = $('#idContainer');
const idLabel = $('#idLabel');
const idValue = $('#idValue');

const ipContainer = $('#ipContainer');
const ipLabel = $('#ipLabel');
const ipValue = $('#ipValue');

const timeValue = $('#timeValue');

const adminContainer = $('#adminContainer');
const issuedValue = $('#issuedValue');

const serverContainer = $('#serverContainer');
const serverValue = $('#serverValue');

const scopeValue = $('#scopeValue');

const reasonValue = $('#reasonValue');

const itemFlag = $('#itemFlag');
const callAdminFlag = $('#callAdminFlag');
const adminChatFlag = $('#adminChatFlag');
const textChatFlag = $('#textChatFlag');
const voiceChatFlag = $('#voiceChatFlag');
const warningFlag = $('#warningFlag');
const banFlag = $('#banFlag');

const removedC = $('.rmEl');
const rOn = $('#removedOnValue');
const rBy = $('#removedByValue');
const rR = $('#removedReasonValue');

const commentContainer = $('#iComments');

const iOptions = $('#infOptions');

const ALL_P_FLAGS = 3968;

const callAdminFlagEdit = $('#callAdminFlagEdit');
const adminChatFlagEdit = $('#adminChatFlagEdit');
const itemFlagEdit = $('#itemFlagEdit');
const textChatFlagEdit = $('#textChatFlagEdit');
const voiceChatFlagEdit = $('#voiceChatFlagEdit');
const banFlagEdit = $('#banFlagEdit');
const restrictionsEditCell = $('#restrictionsEditCell');
const restrictionsEdit = $('#restrictionsEdit');
const restrictionsCancel = $('#restrictionsCancel');

let server_data = [];

function resetViewModal() {
    $('.ptag').addClass('is-hidden');
    $('.ftag').addClass('is-hidden');

    idContainer.removeClass('is-hidden');
    ipContainer.removeClass('is-hidden');
    adminContainer.removeClass('is-hidden');
    serverContainer.removeClass('is-hidden');
    removedC.addClass('is-hidden');
    $('.edit').addClass('is-hidden');
    commentContainer.empty();
    $('#privateCheck').prop('checked', false);
    commentContainer.addClass('is-hidden');
    $('#commentState').removeClass('fa-sort-down').addClass('fa-sort-up');
    $('#commentCount').text('0');
    $('#commentText').prop('disabled', false).val('');
    $('#doPost').removeClass('is-loading').prop('disabled', true);
    $('#FileButton').removeClass('is-loading');
    $('#doFileUpload').prop('disabled', false);
    iOptions.addClass('is-hidden');
    $('.edit-cell').addClass('is-hidden');
    $('.data-cell').removeClass('is-hidden');
    $('#idValue').empty();
    $('#ipValue').empty();
    restrictionsCancel.addClass('is-hidden');
    $('#cancelRemoval').removeAttr('disabled');
    $('#removeButton').removeAttr('disabled').removeClass('is-loading');
    $('#removalReason').val('');
}

async function setupViewModal(infraction) {
    const gbServers = await gbRequest('GET', '/api/server/?enabled_only=true');

    if (!gbServers.ok) {
        const errorData = await gbServers.json();
        throw new Error(errorData.detail || defaultAPIError);
    }

    server_data = await gbServers.json();

    viewModal.attr('data-infraction', infraction['id']);

    // Avatar
    if (infraction['player'].hasOwnProperty('gs_avatar')) {
        userAvatar.attr('src', '/file/uploads/' + infraction['player']['gs_avatar']['file_id'] + '/avatar.webp');
    } else {
        userAvatar.attr('src', '/static/images/fallback_av.png');
    }

    // Name
    if (infraction['player'].hasOwnProperty('gs_name')) {
        userName.text(infraction['player']['gs_name']);
    } else if (infraction['player'].hasOwnProperty('gs_id')) {
        userName.text('Unknown Player');
    } else if (infraction['player'].hasOwnProperty('ip')) {
        userName.text(infraction['player']['ip']);
    } else {
        userName.text('IP Address');
    }

    // Created
    createdAt.text(moment.unix(infraction['created']).format('LLL'));

    // A couple of flags

    if (infraction['flags'] & (INFRACTION.SYSTEM)) {
        systemTag.removeClass('is-hidden');
    }

    if (infraction['flags'] & (INFRACTION.REMOVED)) {
        removedTag.removeClass('is-hidden');
    }

    if (infraction['flags'] & (INFRACTION.VPN)) {
        vpnTag.removeClass('is-hidden');
    }

    if (infraction['flags'] & (INFRACTION.WEB)) {
        webTag.removeClass('is-hidden');
    }

    let isExpired = false;

    if (
        infraction.hasOwnProperty('time_left')
        && infraction['time_left'] <= 0
        && infraction['flag'] & INFRACTION.PLAYTIME_DURATION
    ) {
        isExpired = true;
    } else if (infraction.hasOwnProperty('expires') && Date.now() / 1000 >= infraction['expires']) {
        isExpired = true;
    }

    if (isExpired) {
        expiredTag.removeClass('is-hidden');
    }

    // Setup GSID and IP
    let search = [];

    if (infraction['player'].hasOwnProperty('gs_id')) {
        let service = 'steam';
        if (infraction['player'].hasOwnProperty('gs_service'))
            service = infraction['player']['gs_service'];

        idLabel.text(
            service.charAt(0).toUpperCase()
            + infraction['player']['gs_service'].slice(1)
            + ' ID'
        );
        search.push('gs_service=' + service);
        search.push('gs_id=' + infraction['player']['gs_id']);

        if (service === 'steam') {
            const steamProfile = document.createElement('a');
            steamProfile.text = infraction['player']['gs_id'];
            steamProfile.setAttribute('href', 'http://steamcommunity.com/profiles/' + infraction['player']['gs_id']);
            steamProfile.setAttribute('target', '_blank');

            idValue.append(steamProfile);
        } else {
            idValue.text(infraction['player']['gs_id']);
        }
    } else {
        idContainer.addClass('is-hidden');
    }

    if (infraction['player'].hasOwnProperty('ip')) {
        search.push('ip=' + infraction['player']['ip']);
        ipValue.text(infraction['player']['ip']);
    } else {
        ipContainer.addClass('is-hidden');
    }

    // Setup the time
    timeValue.removeClass('has-tooltip-info');
    timeValue.removeAttr('data-tooltip');
    if (infraction['flags'] & (INFRACTION.PERMANENT)) {
        timeValue.text('Permanent');
    } else if (infraction['flags'] & (INFRACTION.SESSION)) {
        timeValue.text('Session');
    } else if (infraction['flags'] & (INFRACTION.PLAYTIME_DURATION)) {
        let s;
        const tl = moment.duration(infraction['time_left'] * 1000);

        s = tl.humanize();

        s = s.charAt(0).toUpperCase() + s.slice(1);

        if (infraction.hasOwnProperty('orig_length')) {
            const ol = moment.duration(infraction['orig_length'] * 1000);

            s = s + ' of ' + ol.humanize();
        }

        if (infraction['time_left'] <= 0) {
            timeValue.text('Expired (Was ' + moment.duration(infraction['orig_length'] * 1000).humanize() + ')');
        }  else {
            if (infraction['time_left'] > 60) {
                // Display exact minutes left in a tooltip
                timeValue.addClass('has-tooltip-info');
                minutesLeft = (Math.round(moment.duration(infraction['time_left']) / 60) + ' minutes left');
                timeValue.attr('data-tooltip', minutesLeft);
            }
            timeValue.text(s);
        }
    } else if (infraction.hasOwnProperty('expires')) {
        const exp = infraction['expires'] * 1000;
        const now = Date.now();
        const c = infraction['created'] * 1000;

        const d = moment.duration(exp - now);

        const ol = moment.duration(exp - c);

        let s;

        s = d.humanize();

        s = s.charAt(0).toUpperCase() + s.slice(1);

        timeValue.text(s + ' of ' + ol.humanize());

        if (exp - now <= 0) {
            timeValue.text('Expired (Was ' + ol.humanize() + ')');
        } else {
            // Display exact minutes left in a tooltip
            timeValue.addClass('has-tooltip-info');
            minutesLeft = Math.round(d / 60000) + ' minutes left';
            timeValue.attr('data-tooltip', minutesLeft);
        }
    } else {
        timeValue.text('NO VALUE');
    }

    if (!(infraction['flags'] & (INFRACTION.SYSTEM)) && infraction.hasOwnProperty('admin')) {
        issuedValue.text((await get_admin(infraction['admin']))['admin_name']);
    } else {
        adminContainer.addClass('is-hidden');
    }

    // Global
    if (infraction['flags'] & (INFRACTION.GLOBAL)) {
        scopeValue.text('All Servers');
    } else {
        scopeValue.text('Only Origin Server');
    }

    if (infraction['flags'] & (INFRACTION.WEB) || !infraction.hasOwnProperty('server')) {
        serverValue.text('Web');
    } else {
        let sv = await gbRequest('GET', '/api/server/' + infraction['server'], null);

        if (!sv.ok) {
            const errorData = await sv.json();
            console.log(errorData.detail || defaultAPIError);
            serverValue.text('Unknown Server');
        } else {
            sv = await sv.json();

            if (sv.hasOwnProperty('friendly_name')) {
                serverValue.text(sv['friendly_name'] + ' (' + sv['ip'] + ')');
            } else {
                serverValue.text(sv['ip']);
            }
        }
    }

    reasonValue.text(infraction['reason']);

    let t = false;

    function unhideIfTrue(b, a) {
        if (b) {
            t = true;
            a.removeClass('is-hidden');
        }
    }

    unhideIfTrue(infraction['flags'] & ALL_P_FLAGS === 0, warningFlag);
    unhideIfTrue(infraction['flags'] & (INFRACTION.VOICE_BLOCK), voiceChatFlag);
    unhideIfTrue(infraction['flags'] & (INFRACTION.CHAT_BLOCK), textChatFlag);
    unhideIfTrue(infraction['flags'] & (INFRACTION.BAN), banFlag);
    unhideIfTrue(infraction['flags'] & (INFRACTION.ADMIN_CHAT_BLOCK), adminChatFlag);
    unhideIfTrue(infraction['flags'] & (INFRACTION.CALL_ADMIN_BAN), callAdminFlag);
    unhideIfTrue(infraction['flags'] & (INFRACTION.ITEM_BLOCK), itemFlag);

    if (!t) {
        unhideIfTrue(true, warningFlag);
    }

    if (infraction['flags'] & (INFRACTION.REMOVED)) {
        removedC.removeClass('is-hidden');
        rR.text(infraction['removal_reason']);
        rOn.text(moment.unix(infraction['removed_on']).format('LLL'));

        if (infraction.hasOwnProperty('removed_by')) {
            rBy.text((await get_admin(infraction['removed_by']))['admin_name']);
        } else {
            rBy.text('System');
        }
    }

    let altSearchUrlParams = '';
    for (let i = 0; i < search.length; i++) {
        altSearchUrlParams = altSearchUrlParams.concat('&' + search[i]);
    }

    let altSearchLink = $('<a>')
        .attr('href', '/infractions/?alt_search=true&depth=3' + altSearchUrlParams)
        .text('(search)');

    $('#total-blocks').empty();

    let totalBlocks = 'Unknown';
    let altBlocks = await gbRequest('GET', '/api/infractions/alt_search?depth=3' + altSearchUrlParams, null);
    if (altBlocks.ok) {
        altBlocksJson = await altBlocks.json();

        if (altBlocksJson.hasOwnProperty('total_matched'))
            totalBlocks = altBlocksJson['total_matched'];
    }
    $('#total-blocks').append($('<p>').text(totalBlocks + ' ').append(altSearchLink));

    addComments(mergeCommentFiles(infraction));

    prepareEditor(infraction);
}

function mergeCommentFiles(infraction) {
    const m = [];

    for (let i = 0; i < infraction['comments'].length; i++) {
        let uid = 0;

        if (infraction['comments'][i].hasOwnProperty('author')) {
            uid = infraction['comments'][i]['author'];
        }

        const c = {
            'type': 'comment',
            'user': uid,
            'created': infraction['comments'][i]['created'],
            'private': infraction['comments'][i]['private'],
            'rendered': infraction['comments'][i]['rendered'],
            'index': i
        };

        if (infraction['comments'][i].hasOwnProperty('edit_data')) {
            c['edit_user'] = infraction['comments'][i]['edit_data']['admin'];
            c['edit_time'] = infraction['comments'][i]['edit_data']['time'];
        }

        m.push(c);
    }


    for (let i = 0; i < infraction['files'].length; i++) {
        let uid = 0;

        if (infraction['files'][i].hasOwnProperty('uploaded_by')) {
            uid = infraction['files'][i]['uploaded_by'];
        }

        const f = {
            'type': 'file',
            'user': uid,
            'created': infraction['files'][i]['created'],
            'private': infraction['files'][i]['private'],
            'rendered': infraction['files'][i]['rendered'],
            'file_id': i
        };

        m.push(f);
    }


    m.sort(function (a, b) {
        return a['created'] - b['created'];
    });

    return m;
}

function addComments(renderableComments) {
    const current_user = parseInt(getMeta('current_user'));
    const active_perms = parseInt(getMeta('active_permissions'));

    for (let i = 0; i < renderableComments.length; i++) {
        $('#commentCount').text(i + 1);
        const rc = renderableComments[i];

        const cArt = document.createElement('article');
        cArt.classList.add('media');

        const leftFigure = document.createElement('figure');
        leftFigure.classList.add('media-left');

        const imageWrapper = document.createElement('p');
        imageWrapper.classList.add('image', 'is-48x48');

        const avatarImage = document.createElement('img');
        avatarImage.classList.add('is-rounded', 'set-default-on-error');
        avatarImage.setAttribute('src', '/static/images/fallback_av.png');

        imageWrapper.appendChild(avatarImage);
        leftFigure.appendChild(imageWrapper);

        const content = document.createElement('div');
        content.classList.add('media-content');

        const innerContent = document.createElement('div');
        innerContent.classList.add('content');

        const textWrapper = document.createElement('p');

        const username = document.createElement('strong');
        const date = document.createElement('small');
        const priv = document.createElement('small');
        const edit = document.createElement('small');

        username.classList.add('text-primary');

        $(username).text('Loading');
        $(date).text(' ' + moment.unix(rc['created']).format('LLL') + ' ');

        if (rc['edit_time']) {
            $(edit).text('(Edited)');
            $(edit).css('color', 'grey');
            edit.classList.add('has-tooltip-dark');
            $(edit).attr('data-tooltip', 'Edited ' + moment.unix(rc['edit_time']).format('LLL'));
            if (rc['edit_user']) {
                get_admin(rc['edit_user']).then(function (adm) {
                    $(edit).attr('data-tooltip', $(edit).attr('data-tooltip') + ' by ' + adm['admin_name']);
                });
            }
        }

        if (rc['private']) {
            $(priv).text('(Private) ');
            priv.classList.add('has-text-danger');
        }

        const br = document.createElement('br');
        const messageContent = document.createElement('span');

        $(messageContent).html(rc['rendered']);

        textWrapper.append(username, date, priv, edit);

        if (
            (
                rc['user'] !== 0
                && rc['user'] === current_user
                && active_perms & PERMISSION.COMMENT
            )
            || active_perms & PERMISSION.WEB_MODERATOR
        ) {
            if (rc['type'] === 'comment') {
                const deleteButton = document.createElement('a');
                deleteButton.classList.add('fas', 'fa-trash', 'text-primary', 'edit-comment');
                $(deleteButton).css('float', 'right').css('opacity', 0.6).css('padding-right', '10px');
                $(deleteButton).click(function(event){
                    startDeleteComment(event, rc['index']);
                });

                textWrapper.append(deleteButton);

                const editButton = document.createElement('a');
                editButton.classList.add('fas', 'fa-pen', 'text-primary', 'edit-comment');
                $(editButton).css('float', 'right').css('opacity', 0.6).css('padding-right', '10px');
                $(editButton).click(function(event){
                    startEditComment(event, rc['index']);
                });

                textWrapper.append(editButton);
            } else if (rc['type'] === 'file') {
                const deleteButton = document.createElement('a');
                deleteButton.classList.add('fas', 'fa-trash', 'text-primary', 'edit-comment');
                $(deleteButton).css('float', 'right').css('opacity', 0.6).css('padding-right', '10px');
                $(deleteButton).click(function(event){
                    startDeleteAttachment(event, rc['file_id']);
                });

                textWrapper.append(deleteButton);
            }
        }

        textWrapper.append(br, messageContent);

        innerContent.appendChild(textWrapper);
        content.appendChild(innerContent);
        cArt.appendChild(leftFigure);
        cArt.appendChild(content);

        commentContainer.append(cArt);

        if (rc['user'] === 0) {
            $(username).text('System');
        } else {
            get_admin(rc['user']).then(function (adm) {
                $(username).text(adm['admin_name']);

                if (!adm.hasOwnProperty('avatar_id')) {
                    return;
                }

                $(avatarImage).attr('src', '/file/uploads/' + adm['avatar_id'] + '/avatar.webp');
            });
        }
    }

    if (renderableComments.length <= 3) {
        const cind = $('#commentState');
        cind.removeClass('fa-sort-up');
        cind.addClass('fa-sort-down');
        commentContainer.removeClass('is-hidden');
    }
}

function startDeleteComment(event, index) {
    event.preventDefault();

    // Load comment info into confirmation window
    const comment = $(event.currentTarget).closest('.media');
    const commentClone = comment.clone();
    commentClone.find('.edit-comment').remove();
    commentClone.css('border', '1px solid var(--text-secondary)').css('padding', '5px');
    const commentPreview = $('#deleteCommentModal .control');
    commentPreview.empty();
    commentPreview.append(commentClone);

    const dcm = $('#deleteCommentModal');
    const db = $('#deleteButton');
    const cd = $('#cancelDelete');

    dcm.addClass('is-active');

    db.off('click').click(function () {
        if (this.hasAttribute('disabled'))
            return;

        cd.attr('disabled', '1');
        db.attr('disabled', '1').addClass('is-loading');

        deleteComment(index).then(function (d) {
            cd.removeAttr('disabled');
            db.removeAttr('disabled').removeClass('is-loading');
            dcm.removeClass('is-active');
            wrapSetupView(d);
        }).catch(function (e) {
            dcm.removeClass('is-active').removeClass('is-loading');
            db.removeAttr('disabled').removeClass('is-loading');
            logException(e);
        });
    });
}

async function deleteComment(index) {
    const infID = $('#infraction_view_modal').attr('data-infraction');
    const mod = {
        'comment_index': index
    };
    const resp = await gbRequest('DELETE', `/api/infractions/${infID}/comment`, mod, true);

    if (!resp.ok) {
        const errorData = await resp.json();
        throw new Error(errorData.detail || defaultAPIError);
    }

    return await resp.json();
}

function startEditComment(event, index) {
    event.preventDefault();

    const comment = $(event.currentTarget).closest('p');
    const originalMessage = comment.find('span').text();

    // Hide comment to replace with text area for edit
    const content = $(comment).closest('.content');
    content.find('p').addClass('is-hidden');

    const editDiv = $('<div>').addClass('edit-comment-div');

    const editTextarea = $('<textarea>');
    editTextarea.addClass('textarea edit-comment-text');
    editTextarea.val(originalMessage);
    editTextarea.attr('maxlength', '280');
    editTextarea.attr('rows', '2');

    const submitEditButton = $('<button>');
    submitEditButton.addClass('button is-success');
    submitEditButton.text('Edit');

    const cancelEditButton = $('<button>').addClass('button is-danger').text('Cancel');
    cancelEditButton.click(function(event) {
        if (this.hasAttribute('disabled'))
            return;

        content.find('p').removeClass('is-hidden');
        editDiv.remove();
    });

    submitEditButton.off('click').click(function(event) {
        if (this.hasAttribute('disabled') || originalMessage === editTextarea.val())
            return;

        editTextarea.attr('disabled', '1');
        cancelEditButton.attr('disabled', '1');
        submitEditButton.attr('disabled', '1').addClass('is-loading');

        editComment(index, editTextarea.val()).then(function (d) {
            content.find('p').removeClass('is-hidden');
            editDiv.remove();
            wrapSetupView(d);
        }).catch(function (e) {
            editTextarea.removeAttr('disabled');
            cancelEditButton.removeAttr('disabled');
            submitEditButton.removeAttr('disabled').removeClass('is-loading');
            logException(e);
        });
    });

    editDiv.append(editTextarea);
    editDiv.append(submitEditButton);
    editDiv.append(cancelEditButton);

    content.append(editDiv);
}

async function editComment(index, message) {
    const infID = $('#infraction_view_modal').attr('data-infraction');
    const mod = {
        'comment_index': index,
        'content': message
    };
    const resp = await gbRequest('PATCH', `/api/infractions/${infID}/comment`, mod, true);

    if (!resp.ok) {
        const errorData = await resp.json();
        throw new Error(errorData.detail || defaultAPIError);
    }

    return await resp.json();
}

function startDeleteAttachment(event, id) {
    event.preventDefault();

    // Load comment info into confirmation window
    const comment = $(event.currentTarget).closest('.media');
    const commentClone = comment.clone();
    commentClone.find('.edit-comment').remove();
    commentClone.css('border', '1px solid var(--text-secondary)').css('padding', '5px');
    const commentPreview = $('#deleteCommentModal .control');
    commentPreview.empty();
    commentPreview.append(commentClone);

    const dcm = $('#deleteCommentModal');
    const db = $('#deleteButton');
    const cd = $('#cancelDelete');

    dcm.addClass('is-active');

    db.off('click').click(function () {
        if (this.hasAttribute('disabled'))
            return;

        cd.attr('disabled', '1');
        db.attr('disabled', '1').addClass('is-loading');

        deleteAttachment(id).then(function (d) {
            cd.removeAttr('disabled');
            db.removeAttr('disabled').removeClass('is-loading');
            dcm.removeClass('is-active');
            wrapSetupView(d);
        }).catch(function (e) {
            dcm.removeClass('is-active').removeClass('is-loading');
            db.removeAttr('disabled').removeClass('is-loading');
            logException(e);
        });
    });
}

async function deleteAttachment(fileID) {
    const infID = $('#infraction_view_modal').attr('data-infraction');
    const mod = {
        'infraction': infID,
        'file_idx': fileID,
        // 'admin': {
        //    'gs_admin': parseInt(getMeta('current_user'))
        // }
    };
    const resp = await gbRequest('DELETE', `/api/infractions/${infID}/attachment`, mod, true);

    if (!resp.ok) {
        const errorData = await resp.json();
        throw new Error(errorData.detail || defaultAPIError);
    }

    return await resp.json();
}

function wrapSetupView(j, start=0) {
    resetViewModal();

    setupViewModal(j).then(function () {

        function _showModal() {
            unsetLoading();
            $('#infraction_view_modal').addClass('is-active');
            $('#htmlRoot').addClass('is-clipped');
        }

        const dur = 200 - ((new Date()).getTime() - start);

        // If it was quicker than 200 ms, then stall for the time left to reduce flicker
        if (dur > 0) {
            setTimeout(_showModal, dur);
        } else {
            _showModal();
        }
    }).catch(logException);
}

function _openInfraction(infraction_id, start, skip_push=false) {

    if (!skip_push) {
        setInfractionUri(infraction_id);
    }

    gbRequest('GET', '/api/infractions/' + infraction_id + '/info', null, false).then(function (r) {
        r.json().then(function (j) {
            wrapSetupView(j, start);
        }).catch(logException);
    }).catch(logException);
}

function openInfraction(infraction_id, skip_push=false) {
    closeModals();

    setLoading();

    _openInfraction(infraction_id, (new Date()).getTime(), skip_push);
}

function setInfractionUri(infraction_id) {
    const urlParams = new URLSearchParams(window.location.search);

    let nurl;

    if (infraction_id) {
        nurl = '/infractions/' + infraction_id + '/';
    } else {
        nurl = '/infractions/';
    }

    let a = false;

    function nc() {
        if (a) {
            return '&';
        } else {
            a = true;
            return '?';
        }
    }

    urlParams.forEach((value, key) => {
        nurl = nurl + nc() + key + '=' + value;
    });

    let state = 'Infraction';

    if (infraction_id) {
        state = infraction_id;
    }

    window.history.replaceState({'gb_state': state}, 'GFLBans - Infraction', nurl);
}

function restoreInfractionUri() {
    setInfractionUri(null);
}

$(document).ready(function () {
    $('#commentToggle').click(function () {
        const cind = $('#commentState');

        if (cind.hasClass('fa-sort-up')) {
            cind.removeClass('fa-sort-up');
            cind.addClass('fa-sort-down');
            commentContainer.removeClass('is-hidden');
        } else {
            cind.addClass('fa-sort-up');
            cind.removeClass('fa-sort-down');
            commentContainer.addClass('is-hidden');
        }
    });

    $('#ivm-back').click(restoreInfractionUri);
    $('#ivm-close').click(restoreInfractionUri);

    window.onpopstate = function (ev) {
        if (ev.state.hasOwnProperty('gb_state')) {
            if (ev.state['gb_state'] === 'Infraction' && $('#infraction_view_modal').hasClass('is-active')) {
                closeModals();
            } else {
                openInfraction(ev.state['gb_state'], true);
            }
        }
    };

    $('#cancelDelete').click(function () {
        if (this.hasAttribute('disabled')) {
            return;
        }

        $('#deleteCommentModal').removeClass('is-active');
    });
});
