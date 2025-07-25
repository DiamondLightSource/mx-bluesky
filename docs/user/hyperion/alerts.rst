Alerts
------

Hyperion can be configured to raise alerts in order to notify staff of issues with data collections or with Hyperion 
itself.

The currently supported alerting backend uses graylog alerting to send email alert notifications.

Graylog Alert Configuration
===========================

When hyperion generates an alert it will generate the alert in the form of a log message that will be logged to graylog
in the normal way.

The log message will have the message ``***ALERT*** summary=<summary> content=<content>`` and will have the following 
metadata as fields in the log message.

.. csv-table:: Log message fields
    :widths: auto
    :header: "Field", "Description"

    "alert_summary", "A single line summary of the alert, that could e.g. be used in an email summary"
    "alert_content", "The plain text body of the alert message"
    "beamline", "Beamline on which the alert was raised"
    "container", "Container ID that was being processed"
    "ispyb_url", "Link to the ISPyB page of the affected sample"
    "graylog_url", "Link to the graylog stream in the minutes up to the event"
    "sample_id", "Sample ID that was being processed"
    "visit", "Visit that was being processed"


In order to configure alerts in Graylog you will need appropriate Graylog permissions to edit Event Definitions and 
Notifications.

Event Definitions define which log messages will trigger a Graylog Event, and the information that is contained in 
the event.

Notifications are triggered by a Graylog Event and define how the information in the event is dispatched to the 
recipient(s).

For the authoritative Graylog documentation, please see https://go2docs.graylog.org/current/interacting_with_your_log_data/alerts.html

Notification Configuration
--------------------------

Go to the Alerts->Notifications tab in Graylog, you should see a searchable list of notifications, clicking on the 
notification you want to edit and click the "Edit Notification" button.

For an email notification, you can edit the subject, recipients, and the plain-text and HTML body.

Inside the subject and body fields, you can include metadata from the event, for example ``${event.timestamp}`` will 
expand to the event timestamp. 

All the fields that are available in the event are available under the ``event.fields`` object, e.g. ``${event.fields.alert_summary}``

Event Definitions
-----------------

In order to access fields from the log message, including the ones explicitly added by Hyperion and also any other 
ones that graylog appends to the message, you must configure the Event Definition.

To configure the Event Definition, go to the Alerts->Event Definitions tab and click on the notification definition, 
then click "Edit Event Definition".

Under Filter & Aggregation you can configure the conditions under which an event will be generated.
Under Fields you can add custom fields to the event, for each additional field that you want to use in the 
notification, you should click Add Custom Field, then populate the fields, see the existing definitions as a guide.
